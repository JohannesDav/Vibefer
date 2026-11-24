#include "gpu/checkpoint.h"
#include "gpu/kernel.h"
#include <gpu/embedded_kernels.h>
#include <array>
#include <iostream>
#include <stdexcept>
#include <string>

int main() {
    using namespace gpu_gfn;
    for (unsigned n : {16u, 18u}) {
        const std::array<uint32_t, 2> limits = n == 16
            ? std::array<uint32_t, 2>{5862084, 11421892}
            : std::array<uint32_t, 2>{2931042, 5710946};
        for (uint32_t b : limits) {
            for (unsigned pack : {1u, 2u, 4u}) {
                kernel_plan plan;
                plan.pack = pack;
                plan.length = (1u << n) / pack;
                for (int offset : {-2, 0, 2}) {
                    const uint32_t base = b + offset;
                    const bool expected = offset != 0 || pack >= 4;
                    if (packed_handoff_fits(base, n, pack) != expected)
                        throw std::runtime_error("Unexpected boundary admission");
                    try {
                        const auto kernel = generate_kernel(base, n, plan);
                        if (!expected || kernel.source.empty())
                            throw std::runtime_error("Unsafe layout admitted");
                    } catch (const std::invalid_argument &error) {
                        if (expected || std::string(error.what()) !=
                                            "Packed digits exceed ordinary two-prime bound")
                            throw;
                    }
                }
            }
        }
    }
    kernel_plan invalid_grid;
    invalid_grid.length = 1u << 16;
    invalid_grid.pack = 1;
    invalid_grid.outer = 16;
    invalid_grid.chunk = 1;
    invalid_grid.inner_blocks = 32;
    try {
        generate_kernel(1026, 16, invalid_grid);
        throw std::runtime_error("Invalid packed launch grid admitted");
    } catch (const std::invalid_argument &error) {
        if (std::string(error.what()) != "Packed launch grid does not divide evenly") throw;
    }
    const uint32_t bases[] = {620000000, 520000000, 100000000, 30000000,
                              8000000, 2800000, 660000, 200000};
    for (const auto &profile : embedded::device_profiles)
        if (profile.kind == implementation::packed &&
            !packed_handoff_fits(bases[profile.exponent - 16], profile.exponent, profile.plan.pack))
            throw std::runtime_error("Benchmark profile admission changed");
    for (const unsigned n : {22u, 23u}) {
        kernel_plan plan;
        plan.pack = 4;
        plan.length = (1u << n) / plan.pack;
        plan.outer = 1024;
        plan.chunk = 1;
        const uint32_t boundary = n == 22 ? 1184u : 1674u;
        try {
            generate_kernel(boundary, n, plan);
            throw std::runtime_error("Unsafe multiply carry admitted");
        } catch (const std::invalid_argument &error) {
            if (std::string(error.what()) != "Ordinary multiply carry exceeds packed digit bound") throw;
        }
        if (generate_kernel(boundary + 2, n, plan).source.empty())
            throw std::runtime_error("Safe multiply carry rejected");
    }
    const auto check23 = [](const auto &profiles) {
        for (const auto &profile : profiles)
            if (profile.exponent == 23 && profile.kind == implementation::packed &&
                generate_kernel(200000, 23, profile.plan).source.empty())
                throw std::runtime_error("GFN-23 profile generation failed");
    };
    check23(embedded::device_profiles);
    check23(embedded::architecture_profiles);
    check23(embedded::project_profiles);
    for (unsigned pack : {4u, 8u}) {
        kernel_plan plan;
        plan.pack = pack;
        plan.length = (1u << 23) / pack;
        plan.outer = pack == 4 ? 1024 : 256;
        plan.chunk = 1;
        for (uint32_t base : {1676u, 100000u, 660000u, 3000000u}) {
            const auto kernel = generate_kernel(base, 23, plan);
            if (kernel.source.empty() || kernel.fields < 2)
                throw std::runtime_error("GFN-23 generation failed");
        }
    }
    std::cout << "PASS: 36 packed handoff boundary cases and all measured frontier profiles\n";
}
