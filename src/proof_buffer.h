#pragma once

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <iomanip>
#include <limits>
#include <memory>
#include <new>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

#if defined(_WIN64)
#include <windows.h>
#elif defined(__linux__)
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

#include "boinc.h"
#include "gint.h"
#if defined(BOINC)
#include "procinfo.h"
#endif

class proof_buffer
{
private:
	// Serialize allocation for cooperating tasks running under the same account.
	class allocation_lock
	{
#if defined(_WIN64)
		HANDLE mutex = CreateMutexW(nullptr, FALSE, L"Local\\VibeferProofBuffer");
		DWORD result = mutex ? WaitForSingleObject(mutex, 0) : WAIT_FAILED;
#elif defined(__linux__)
		int fd = open(("/tmp/vibefer-proof-buffer-" + std::to_string(getuid())).c_str(),
					  O_WRONLY | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
		bool locked = fd >= 0 && flock(fd, LOCK_EX | LOCK_NB) == 0;
#endif
	public:
		bool acquired() const
		{
#if defined(_WIN64)
			return result == WAIT_OBJECT_0 || result == WAIT_ABANDONED;
#elif defined(__linux__)
			return locked;
#else
			return false;
#endif
		}

		~allocation_lock()
		{
#if defined(_WIN64)
			if (acquired()) ReleaseMutex(mutex);
			if (mutex) CloseHandle(mutex);
#elif defined(__linux__)
			if (fd >= 0) close(fd);
#endif
		}
	};

	static uint64_t available_ram()
	{
#if defined(_WIN64)
		MEMORYSTATUSEX status{};
		status.dwLength = sizeof(status);
		if (GlobalMemoryStatusEx(&status)) return status.ullAvailPhys;
#elif defined(__linux__)
		std::ifstream meminfo("/proc/meminfo");
		for (std::string name; meminfo >> name; meminfo.ignore(4096, '\n'))
		{
			if (name != "MemAvailable:") continue;
			uint64_t kib = 0;
			if (meminfo >> kib) return kib * 1024;
			break;
		}
#endif
		return 0;
	}

	static std::string mib(const double bytes)
	{
		std::ostringstream out;
		out << std::fixed << std::setprecision(1) << bytes / (1024 * 1024) << " MiB";
		return out.str();
	}

#if defined(BOINC)
	struct memory_share
	{
		size_t tasks = 0;
		double own = 0, allowance = 0;

		std::string describe() const
		{
			return "BOINC budget " + mib(allowance) + " per task across " +
				   std::to_string(tasks) + (tasks == 1 ? " task" : " tasks");
		}
	};

	int _client_pid = 0;
	double _preference_limit = 0, _initial_working_set = 0;

	void read_boinc_preferences()
	{
		APP_INIT_DATA init{};
		if (boinc_get_init_data_p(&init) != 0) return;
		_client_pid = init.client_pid;
		const double fraction = std::min(init.global_prefs.ram_max_used_busy_frac,
										 init.global_prefs.ram_max_used_idle_frac);
		if (fraction > 0 && init.host_info.m_nbytes > 0)
			_preference_limit = init.host_info.m_nbytes * fraction;
	}

	memory_share boinc_memory_share() const
	{
#if defined(_WIN64)
		const int self = static_cast<int>(GetCurrentProcessId());
#elif defined(__linux__)
		const int self = getpid();
#else
		const int self = 0;
#endif
		if (_client_pid <= 0 || self == 0) return {};
		BOINC_STATUS status{};
		boinc_get_status(&status);
		double limit = status.max_working_set_size;
		if (_preference_limit > 0)
			limit = limit > 0 ? std::min(limit, _preference_limit) : _preference_limit;
		if (limit <= 0) return {};

		// Use the same process-tree working sets that the BOINC client samples.
		// Keep resident jobs in the budget, even if temporarily suspended.
		PROC_MAP processes;
		if (procinfo_setup(processes) != 0) return {};
		const auto client = processes.find(_client_pid);
		const auto own = processes.find(self);
		if (client == processes.end() || own == processes.end() ||
			own->second.parentid != _client_pid) return {};

		std::vector<double> peers;
		for (const int pid : client->second.children)
		{
			if (pid == self) continue;
			PROCINFO peer;
			peer.id = pid;
			procinfo_app(peer, nullptr, processes, nullptr);
			peers.push_back(peer.working_set_size);
		}

		const size_t tasks = peers.size() + 1;
		size_t remaining = tasks;
		std::sort(peers.begin(), peers.end(), std::greater<double>());
		// Reserve actual usage for peers already above an equal share.
		for (const double working_set : peers)
		{
			if (working_set <= limit / remaining) break;
			limit = std::max(0.0, limit - working_set);
			--remaining;
		}
		return {tasks, std::max(own->second.working_set_size, status.working_set_size), limit / remaining};
	}
#endif

	using clock = std::chrono::steady_clock;
	std::unique_ptr<int32_t[]> _digits, _completed;
	std::vector<std::optional<uint32_t>> _checksums;
	size_t _size = 0, _bytes = 0;
	clock::time_point _next_check{};

	int32_t * entry(const size_t index) const
	{
		return index < points() ? _digits.get() + index * _size
								: _completed.get() + (index - points()) * _size;
	}

public:
	std::string allocate(const size_t size, const size_t entries, const bool is_boinc)
	{
		if (entries > std::numeric_limits<size_t>::max() / sizeof(int32_t) / size)
			return "disk (proof buffer too large)";
		const size_t bytes = size * entries * sizeof(int32_t);
		const double needed = double(bytes) + bytes / 3;
		std::string detail;
#if defined(BOINC)
		if (is_boinc)
		{
			read_boinc_preferences();
			const memory_share share = boinc_memory_share();
			if (!share.tasks) return "disk (BOINC task memory budget unavailable)";
			_initial_working_set = share.own;
			const double total_needed = needed + share.own;
			detail = "RAM mode needs " + mib(total_needed) + " with headroom; " + share.describe();
			if (total_needed > share.allowance) return "disk (" + detail + ")";
		}
#else
		(void)is_boinc;
#endif

		allocation_lock lock;
		if (!lock.acquired()) return "disk (proof memory reservation unavailable)";
		const uint64_t available = available_ram();
		const std::string host = "buffer needs " + mib(needed) + " with headroom; host has " + mib(available) + " available";
		if (needed > available) return "disk (" + host + ")";
		if (detail.empty()) detail = host;

		try
		{
			std::vector<std::optional<uint32_t>> checksums(entries);
			auto digits = std::unique_ptr<int32_t[]>(new int32_t[size * (entries - 2)]);
			auto completed = std::unique_ptr<int32_t[]>(new int32_t[size * 2]);
			_checksums = std::move(checksums);
			_digits = std::move(digits);
			_completed = std::move(completed);
		}
		catch (const std::bad_alloc &) { return "disk (could not allocate " + mib(bytes) + " proof buffer)"; }
		_size = size;
		_bytes = bytes;
		// Back the reservation before the next task checks available memory.
		volatile int32_t * const digits = _digits.get(), * const completed = _completed.get();
		for (size_t i = 0; i < size * points(); i += 1024) digits[i] = 0;
		for (size_t i = 0; i < size * 2; i += 1024) completed[i] = 0;
		_next_check = clock::now() + std::chrono::seconds(1);
		return "host RAM (" + detail + ")";
	}

	bool active() const { return bool(_digits); }
	size_t points() const { return _checksums.size() - 2; }
	bool has_completed() const { return _completed && _checksums.back().has_value(); }

	std::string disk_reason(const bool is_boinc)
	{
		if (!active()) return {};
		const auto now = clock::now();
		if (now < _next_check) return {};
		_next_check = now + std::chrono::seconds(1);

		const size_t reserve = _bytes / 3;
		const uint64_t available = available_ram();
		if (available < reserve)
			return "needs " + mib(reserve) + " free for headroom; host has " + mib(available) + " available";
#if defined(BOINC)
		if (is_boinc)
		{
			const memory_share share = boinc_memory_share();
			if (!share.tasks) return "BOINC task memory budget unavailable";
			const double needed = std::max(_initial_working_set + _bytes, share.own) + reserve;
			if (needed > share.allowance)
				return "RAM mode needs " + mib(needed) + " with headroom; " + share.describe();
		}
#else
		(void)is_boinc;
#endif
		return {};
	}

	void release_points()
	{
		// Keep the two PRP registers for a clean quit during proof generation.
		_digits.reset();
		if (!has_completed()) _completed.reset();
	}

	bool contains(const size_t index) const
	{
		return (active() || (_completed && index >= points())) && _checksums.at(index).has_value();
	}

	void store(const size_t index, const gint & value)
	{
		auto & checksum = _checksums.at(index);
		int32_t * const dst = entry(index);
		const size_t bytes = _size * sizeof(int32_t);
		std::memcpy(dst, value.data(), bytes);
		checksum = file::rc_crc32(0, reinterpret_cast<const char *>(dst), bytes);
	}

	void load(const size_t index, gint & value) const
	{
		if (!contains(index)) throw std::runtime_error("Missing proof checkpoint in memory");
		const auto expected = _checksums[index];
		const int32_t * const src = entry(index);
		const size_t bytes = _size * sizeof(int32_t);
		std::memcpy(value.data(), src, bytes);
		const uint32_t checksum = file::rc_crc32(0, reinterpret_cast<const char *>(value.data()), bytes);
		if (checksum != *expected)
			throw std::runtime_error("Proof checkpoint in memory failed its checksum");
		value.reset();
	}
};
