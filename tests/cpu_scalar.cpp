#include <array>
#include <cstdio>
#include <limits>

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

int main()
{
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
