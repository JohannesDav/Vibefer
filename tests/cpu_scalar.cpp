#include <array>
#include <cstdio>
#include <limits>

#include "gint.h"

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
}
