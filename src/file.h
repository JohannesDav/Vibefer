/*
Copyright 2022, Yves Gallot

genefer is free source code, under the MIT license (see LICENSE). You can redistribute, use and/or modify it.
Please give feedback to the authors if improvement is realized. It is distributed in the hope that it will be useful.
*/

#pragma once

#include <array>
#include <iomanip>

#include <gmp.h>

// #if defined(_WIN64)
// #include <IO.h>
// #else
// #include <unistd.h>
// #endif

#include "pio.h"

class file
{
private:
	const std::string _filename;
	FILE * const _cFile;
	const bool _fatal;
	// const bool _isSync;
	uint32_t _crc32 = 0;

public:
	file(const std::string & filename, const char * const mode, const bool fatal)
		: _filename(filename), _cFile(pio::open(filename.c_str(), mode)), _fatal(fatal), _crc32(0) //, _isSync(std::string(mode) == "wb")
	{
		if (_cFile == nullptr) error("cannot open file");
	}

	file(const std::string & filename)
		: _filename(filename), _cFile(pio::open(filename.c_str(), "rb")), _fatal(false), _crc32(0) //, _isSync(false)
	{
		// _cFile may be null
	}

	virtual ~file()
	{
		if (_cFile != nullptr)
		{
// 			if (_isSync)
// 			{
// #if defined(_WIN64)
// 				_commit(_fileno(_cFile));
// #else
// 				fsync(fileno(_cFile));
// #endif
// 			}
			if (std::fclose(_cFile) != 0) error("cannot close file");
		}
	}

	void error(const std::string & str) const
	{
		std::ostringstream ss; ss << _filename << ": " << str;
		pio::error(ss.str(), _fatal);
	}

	bool exists() const { return (_cFile != nullptr); }

	uint32_t crc32() const { return _crc32; }

	// Rosetta Code, CRC-32, C
	static uint32_t rc_crc32(const uint32_t crc32, const char * const buf, const size_t len)
	{
		static const auto table = [] {
			std::array<uint32_t, 256> values{};
			for (size_t i = 0; i < values.size(); ++i)
			{
				uint32_t rem = static_cast<uint32_t>(i);  // remainder from polynomial division
				for (size_t j = 0; j < 8; ++j)
				{
					if (rem & 1)
					{
						rem >>= 1;
						rem ^= 0xedb88320;
					}
					else rem >>= 1;
				}
				values[i] = rem;
			}
			return values;
		}();

		uint32_t crc = ~crc32;
		for (size_t i = 0; i < len; ++i)
		{
			const uint8_t octet = static_cast<uint8_t>(buf[i]);  // Cast to unsigned octet
			crc = (crc >> 8) ^ table[(crc & 0xff) ^ octet];
		}
		return ~crc;
	}

	// Fingerprint all raw bytes independently of the certificate's on-disk checksum.
	uint32_t content_crc32()
	{
		if (std::fseek(_cFile, 0, SEEK_SET) != 0)
			error("cannot seek for content checksum");
		char buffer[16384];
		uint32_t checksum = 0;
		for (size_t bytes; (bytes = std::fread(buffer, 1, sizeof(buffer), _cFile)) != 0;)
			checksum = rc_crc32(checksum, buffer, bytes);
		if (std::ferror(_cFile)) error("cannot read content checksum");
		return checksum;
	}

	bool read(char * const ptr, const size_t size)
	{
		const size_t ret = std::fread(ptr , sizeof(char), size, _cFile);
		_crc32 = rc_crc32(_crc32, ptr, ret);
		if (ret == size * sizeof(char)) return true;
		error("failure of a read operation");
		return false;
	}

	bool write(const char * const ptr, const size_t size)
	{
		const size_t ret = std::fwrite(ptr , sizeof(char), size, _cFile);
		_crc32 = rc_crc32(_crc32, ptr, size);
		if (ret == size * sizeof(char)) return true;
		error("failure of a write operation");
		return false;
	}

	bool read(mpz_t & z)
	{
		if (mpz_inp_raw(z, _cFile) != 0) return true;
		_crc32 = _crc32 ^ static_cast<uint32_t>(mpz_fdiv_ui(z, 0xfedcba98));	// fake crc32
		error("failure of a read operation");
		return false;
	}

	bool write(const mpz_t & z)
	{
		if (mpz_out_raw(_cFile, z) != 0) return true;
		_crc32 = _crc32 ^ static_cast<uint32_t>(mpz_fdiv_ui(z, 0xfedcba98));	// fake crc32
		error("failure of a write operation");
		return false;
	}

	bool print(const char * const str)
	{
		const int ret = std::fprintf(_cFile, "%s", str);
		if (ret >= 0) return true;
		error("failure of a print operation");
		return false;
	}

	void write_crc32()
	{
		uint32_t crc32 = ~_crc32 ^ 0xa23777ac;
		write(reinterpret_cast<const char *>(&crc32), sizeof(crc32));
	}

	bool check_crc32()
	{
		uint32_t crc32 = 0, ocrc32 = ~_crc32 ^ 0xa23777ac;	// before the read operation
		if (!read(reinterpret_cast<char *>(&crc32), sizeof(crc32))) return false;
		const bool success = (crc32 == ocrc32);
		if (!success) error("bad file (crc32)");
		return success;
	}
};
