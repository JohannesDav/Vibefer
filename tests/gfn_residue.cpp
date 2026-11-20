#include <cstdlib>
#include <gmp.h>

// Independent modular exponentiation for the small known-answer tests.
int main(int argc, char **argv)
{
    if (argc != 4)
        return 2;
    const unsigned long base = std::strtoul(argv[1], nullptr, 10);
    const unsigned long witness = std::strtoul(argv[2], nullptr, 10);
    const unsigned long divisor = std::strtoul(argv[3], nullptr, 10);
    if (divisor == 0)
        return 2;
    mpz_t modulus, exponent, residue;
    mpz_inits(modulus, exponent, residue, nullptr);
    mpz_ui_pow_ui(exponent, base, 4096);
    mpz_add_ui(modulus, exponent, 1);
    mpz_divexact_ui(exponent, exponent, divisor);
    mpz_set_ui(residue, witness);
    mpz_powm(residue, residue, exponent, modulus);
    const bool is_one = mpz_cmp_ui(residue, 1) == 0;
    mpz_fdiv_r_2exp(residue, residue, 64);
    gmp_printf("%d %Zx\n", is_one, residue);
    mpz_clears(modulus, exponent, residue, nullptr);
}
