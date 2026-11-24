#include <array>
#include <cstdio>
#include <limits>
#include <random>

#include "gint.h"
#if defined(TEST_CPU_TRANSFORMS)
#include "transform.h"
#include <memory>
#endif

using digits = std::array<int32_t, 8>;

static void decode(mpz_t value, const int32_t *data, const uint32_t base)
{
	mpz_set_ui(value, 0);
	mpz_t digit; mpz_init(digit);
	for (size_t i = digits{}.size(); i-- > 0;)
	{
		mpz_mul_ui(value, value, base);
		mpz_set_si(digit, data[i]);
		mpz_add(value, value, digit);
	}
	mpz_clear(digit);
}

static bool check(const uint32_t base, const int32_t scalar, const digits &input)
{
	gint value(input.size(), base);
	std::copy(input.begin(), input.end(), value.data());
	value.balance(scalar);

	mpz_t modulus, expected, actual;
	mpz_inits(modulus, expected, actual, nullptr);
	mpz_ui_pow_ui(modulus, base, input.size());
	mpz_add_ui(modulus, modulus, 1);
	decode(expected, input.data(), base);
	mpz_mul_si(expected, expected, scalar);
	mpz_mod(expected, expected, modulus);
	decode(actual, value.data(), base);
	mpz_mod(actual, actual, modulus);
	const bool equal = mpz_cmp(expected, actual) == 0;
	if (!equal) gmp_fprintf(stderr, "Scalar %d at base %u: expected %Zd, got %Zd\n", scalar, base, expected, actual);
	mpz_clears(modulus, expected, actual, nullptr);
	return equal;
}

#if defined(TEST_CPU_TRANSFORMS)
static void decode_range(mpz_t value, const int32_t *data, size_t size, uint32_t base)
{
	mpz_set_ui(value, 0);
	if (size <= 32)
	{
		mpz_t digit; mpz_init(digit);
		for (size_t i = size; i-- > 0;)
		{
			mpz_mul_ui(value, value, base);
			mpz_set_si(digit, data[i]);
			mpz_add(value, value, digit);
		}
		mpz_clear(digit);
		return;
	}
	const size_t half = size / 2;
	mpz_t high, place; mpz_inits(high, place, nullptr);
	decode_range(value, data, half, base);
	decode_range(high, data + half, size - half, base);
	if (mpz_sgn(high) != 0)
	{
		mpz_ui_pow_ui(place, base, half);
		mpz_addmul(value, high, place);
	}
	mpz_clears(high, place, nullptr);
}

static bool transform_case(const std::string &implementation, unsigned int n, uint32_t base,
						   int32_t scalar, bool dense, bool check_error, size_t threads = 1)
{
	const size_t size = size_t(1) << n;
	gint value(size, base);
	std::fill_n(value.data(), size, 0);
	if (dense)
		std::fill_n(value.data(), 256, base / 2 - 1);
	else
	{
		value.data()[0] = -513;
		value.data()[size / 2] = 941;
		value.data()[size - 1] = -313;
	}
	mpz_t modulus, expected, actual;
	mpz_inits(modulus, expected, actual, nullptr);
	mpz_ui_pow_ui(modulus, base, size);
	mpz_add_ui(modulus, modulus, 1);
	decode_range(expected, value.data(), size, base);
	mpz_mul(expected, expected, expected);
	mpz_mul_si(expected, expected, scalar);
	mpz_mod(expected, expected, modulus);

	std::string found;
	const std::unique_ptr<transform> engine(transform::create_cpu(base, n, threads, implementation, 3, check_error, found));
	engine->setInt(value);
	if (scalar == 1 || scalar == 2) engine->squareDup(scalar == 2);
	else engine->squareMul(scalar);
	engine->getInt(value);
	decode_range(actual, value.data(), size, base);
	mpz_mod(actual, actual, modulus);
	const bool equal = found == implementation && mpz_cmp(expected, actual) == 0;
	std::printf("%s GFN-%u b=%u scalar=%d errors=%d threads=%zu: %s\n", found.c_str(), n, base, scalar, check_error, threads, equal ? "PASS" : "FAIL");
	mpz_clears(modulus, expected, actual, nullptr);
	return equal;
}

static bool check_transforms()
{
	std::istringstream implementations(transform::implementations());
	for (std::string implementation; implementations >> implementation;)
	{
		if (implementation == "i32") continue;
		for (bool check_error : {false, true})
			if (!transform_case(implementation, 12, 1040, 1, true, check_error) ||
				!transform_case(implementation, 12, 1040, 2, true, check_error) ||
				!transform_case(implementation, 12, 1040, 23, true, check_error) ||
				!transform_case(implementation, 12, 1040, 1 << 20, true, check_error) ||
				!transform_case(implementation, 12, 1040, std::numeric_limits<int32_t>::max(), true, check_error) ||
				!transform_case(implementation, 19, 38786700, 23, false, check_error) ||
				!transform_case(implementation, 12, 1040, 1 << 20, true, check_error, 2) ||
				!transform_case(implementation, 12, 1040, 23, true, check_error, 9))
				return false;
	}
	return true;
}
#endif

static bool check_residue_comparison()
{
	constexpr size_t size = 1u << 16;
	constexpr uint32_t base = 620000000;
	gint one(size, base), other(size, base);
	std::fill_n(one.data(), size, 0);
	std::fill_n(other.data(), size, 0);
	one.data()[0] = 1;
	other.data()[2] = 1;
	if (one.gethash64() != other.gethash64() || one.equals(other)) return false;

	// The same residue in noncanonical digits still compares equal.
	other.reset();
	other.data()[2] = 0;
	other.data()[1] = 1;
	other.data()[0] = 1 - static_cast<int32_t>(base);
	return one.equals(other);
}

static bool check_balance_wrap()
{
	// Reference for the original scalar-1 rule, capped to detect a cycle.
	auto original = [](std::array<int32_t, 8> & digits, const int32_t base) {
		int64_t carry = 0;
		auto step = [&](int32_t & digit) {
			carry += digit;
			int32_t r = static_cast<int32_t>(carry % base);
			if (r > base / 2) r -= base;
			if (r <= -base / 2) r += base;
			digit = r;
			carry = (carry - r) / base;
		};
		for (auto & digit : digits) step(digit);
		for (int wrap = 0; carry && wrap < 4; ++wrap)
		{
			carry = -carry;
			for (auto & digit : digits)
			{
				step(digit);
				if (!carry) break;
			}
		}
		return carry == 0;
	};

	std::mt19937 random(12345);
	for (const int32_t base : {1024, 1534, 620000000, 2000000000})
	{
		gint value(8, static_cast<uint32_t>(base));
		auto check_input = [&](const digits & input) {
			auto expected = input;
			if (!original(expected, base)) return false;
			std::copy(input.begin(), input.end(), value.data());
			value.reset();
			value.balance();
			return std::equal(expected.begin(), expected.end(), value.data());
		};
		std::uniform_int_distribution<int32_t> distribution(INT32_MIN, INT32_MAX);
		for (int i = 0; i < 20000; ++i)
		{
			digits input{};
			for (auto & digit : input) digit = distribution(random);
			if (!check_input(input)) return false;
		}
		for (const int32_t endpoint : {1 - base / 2, base / 2})
		{
			for (int carry = -4; carry <= 4; ++carry)
			{
				for (int offset = -3; offset <= 3; ++offset)
				{
					digits input;
					input.fill(endpoint);
					input.front() += offset;
					if (base > 100000000) continue; // Synthetic carry must fit int32_t.
					input.back() += carry * base;
					auto expected = input;
					if (original(expected, base) && !check_input(input)) return false;
				}
			}
		}
		digits edge;
		edge.fill(base / 2);
		++edge[0];
		auto old_edge = edge;
		if (original(old_edge, base)) return false;
		std::copy(edge.begin(), edge.end(), value.data());
		value.reset();
		value.balance();
		gint unbalanced(8, static_cast<uint32_t>(base));
		std::copy(edge.begin(), edge.end(), unbalanced.data());
		if (std::find(value.data(), value.data() + 8, -base / 2) == value.data() + 8 ||
			!value.equals(unbalanced)) return false;
	}
	return true;
}

int main()
{
	const char text[] = "123456789";
	const uint32_t first = file::rc_crc32(0, text, 4);
	if (file::rc_crc32(first, text + 4, 5) != 0xcbf43926u ||
		file::rc_crc32(0, text, 9) != 0xcbf43926u)
	{
		std::fputs("FAIL CRC-32 reference vector\n", stderr);
		return EXIT_FAILURE;
	}
	std::puts("PASS CRC-32 reference vector and incremental checksum");
	if (!check_balance_wrap())
	{
		std::fputs("FAIL scalar-1 balance compatibility or carry cycle\n", stderr);
		return EXIT_FAILURE;
	}
	std::puts("PASS scalar-1 balance matches 80,000 original outputs and resolves the carry cycle");
	if (!check_residue_comparison())
	{
		std::fputs("FAIL canonical residue comparison\n", stderr);
		return EXIT_FAILURE;
	}
	std::puts("PASS canonical residue comparison rejects the Gerbicz–Li hash collision");
	constexpr int32_t max = std::numeric_limits<int32_t>::max();
	constexpr int32_t min = std::numeric_limits<int32_t>::min();
	// One odd product just above 2^53 and one just below it.
	if (!check(2000000000, max, {4194305, 4194304, -4194305, -4194304, 1, -1, max, min}) ||
		!check(1026, min, {min, max, -1, 1, -4194305, 4194305, min, max}) ||
		!check(38786700, 23, {19393350, -19393350, 1, -1, 0, 1234, -5678, 19393350}))
		return EXIT_FAILURE;
	std::puts("PASS CPU scalar multiplication matches GMP");
#if defined(TEST_CPU_TRANSFORMS)
	if (!check_transforms()) return EXIT_FAILURE;
#endif
}
