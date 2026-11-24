#include "gint.h"
#include <algorithm>
#include <cstdio>

int main()
{
	constexpr uint32_t base = 1025;
	gint value(8, base);
	for (int32_t digit : {-512, 512, 513})
	{
		std::fill_n(value.data(), value.getSize(), 0);
		value.data()[0] = digit;
		value.reset();
		value.balance();
		const int32_t expected = digit == 513 ? -512 : digit;
		if (value.data()[0] != expected || value.data()[1] != (digit == 513))
			return EXIT_FAILURE;
	}
	std::puts("PASS cyclo balances odd bases symmetrically");
}
