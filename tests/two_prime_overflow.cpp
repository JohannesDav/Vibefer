#include "transformGPU.h"
#include <algorithm>
#include <iostream>

// Use the unbalanced input that exposed the two-prime normalization overflow.
// setInt() would balance it first and remove the large coefficients.
class two_prime_probe : public transformGPUs<2, true> {
public:
    using transformGPUs::transformGPUs;
    using transformGPUs::setZi;
};

int main()
{
    constexpr uint32_t n = 19, base = 3500000, size = 1u << n;
    // The largest convolution coefficient overflows a signed 64-bit integer
    // when doubled. In the residue ring the input is base^size - 1 == -2.
    static_assert(uint64_t(size) * (base - 1) * (base - 1) >= (uint64_t(1) << 62));
    two_prime_probe transform(base, n, false, 0, 1, nullptr, nullptr, false);
    gint value(size, base);
    std::fill_n(value.data(), size, base - 1);
    transform.setZi(value.data());
    transform.getInt(value);
    if (!std::all_of(value.data(), value.data() + size,
                     [](int32_t digit) { return digit == base - 1; })) {
        std::cerr << "Two-prime normalization: worst-case input was changed on upload\n";
        return 1;
    }
    transform.squareDup(true);
    transform.getInt(value);
    value.unbalance();
    if (value.data()[0] != 8 || std::any_of(value.data() + 1, value.data() + size,
                                           [](int32_t digit) { return digit != 0; })) {
        std::cerr << "Two-prime normalization: expected doubled square to be 8\n";
        return 1;
    }
    std::cout << "PASS two-prime normalization at the signed overflow boundary\n";
}
