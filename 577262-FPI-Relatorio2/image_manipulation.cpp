#define STB_IMAGE_IMPLEMENTATION
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image.h"
#include "stb_image_write.h"

#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <array>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <omp.h> // Adicionado para suporte nativo a threads

#include "image_manipulation.h"

// =====================================================================
// DEFINIÇÕES DE KERNELS (MANTIDAS INTACTAS)
// =====================================================================
const float GAUSSIAN_KERNEL_3X3[3][3] = {
    {0.0625f, 0.125f, 0.0625f},
    {0.125f,  0.25f,  0.125f},
    {0.0625f, 0.125f, 0.0625f}
};

const float GAUSSIAN_KERNEL_5X5[5][5] = {
    {1.0f/256.0f,  4.0f/256.0f,  6.0f/256.0f,  4.0f/256.0f, 1.0f/256.0f},
    {4.0f/256.0f, 16.0f/256.0f, 24.0f/256.0f, 16.0f/256.0f, 4.0f/256.0f},
    {6.0f/256.0f, 24.0f/256.0f, 36.0f/256.0f, 24.0f/256.0f, 6.0f/256.0f},
    {4.0f/256.0f, 16.0f/256.0f, 24.0f/256.0f, 16.0f/256.0f, 4.0f/256.0f},
    {1.0f/256.0f,  4.0f/256.0f,  6.0f/256.0f,  4.0f/256.0f, 1.0f/256.0f}
};

const float GAUSSIAN_KERNEL_7X7[7][7] = {
    {1.0f/4096.0f,   6.0f/4096.0f,  15.0f/4096.0f,  20.0f/4096.0f,  15.0f/4096.0f,   6.0f/4096.0f, 1.0f/4096.0f},
    {6.0f/4096.0f,  36.0f/4096.0f,  90.0f/4096.0f, 120.0f/4096.0f,  90.0f/4096.0f,  36.0f/4096.0f, 6.0f/4096.0f},
    {15.0f/4096.0f, 90.0f/4096.0f, 225.0f/4096.0f, 300.0f/4096.0f, 225.0f/4096.0f, 90.0f/4096.0f, 15.0f/4096.0f},
    {20.0f/4096.0f,120.0f/4096.0f, 300.0f/4096.0f, 400.0f/4096.0f, 300.0f/4096.0f,120.0f/4096.0f,20.0f/4096.0f},
    {15.0f/4096.0f, 90.0f/4096.0f, 225.0f/4096.0f, 300.0f/4096.0f, 225.0f/4096.0f, 90.0f/4096.0f, 15.0f/4096.0f},
    {6.0f/4096.0f,  36.0f/4096.0f,  90.0f/4096.0f, 120.0f/4096.0f,  90.0f/4096.0f,  36.0f/4096.0f, 6.0f/4096.0f},
    {1.0f/4096.0f,   6.0f/4096.0f,  15.0f/4096.0f,  20.0f/4096.0f,  15.0f/4096.0f,   6.0f/4096.0f, 1.0f/4096.0f}
};

const float GAUSSIAN_KERNEL_9X9[9][9] = {
    {1.0f/65536.0f,   8.0f/65536.0f,  28.0f/65536.0f,  56.0f/65536.0f,  70.0f/65536.0f,  56.0f/65536.0f,  28.0f/65536.0f,   8.0f/65536.0f, 1.0f/65536.0f},
    {8.0f/65536.0f,  64.0f/65536.0f, 224.0f/65536.0f, 448.0f/65536.0f, 560.0f/65536.0f, 448.0f/65536.0f, 224.0f/65536.0f,  64.0f/65536.0f, 8.0f/65536.0f},
    {28.0f/65536.0f,224.0f/65536.0f, 784.0f/65536.0f,1568.0f/65536.0f,1960.0f/65536.0f,1568.0f/65536.0f, 784.0f/65536.0f,224.0f/65536.0f,28.0f/65536.0f},
    {56.0f/65536.0f,448.0f/65536.0f,1568.0f/65536.0f,3136.0f/65536.0f,3920.0f/65536.0f,3136.0f/65536.0f,1568.0f/65536.0f,448.0f/65536.0f,56.0f/65536.0f},
    {70.0f/65536.0f,560.0f/65536.0f,1960.0f/65536.0f,3920.0f/65536.0f,4900.0f/65536.0f,3920.0f/65536.0f,1960.0f/65536.0f,560.0f/65536.0f,70.0f/65536.0f},
    {56.0f/65536.0f,448.0f/65536.0f,1568.0f/65536.0f,3136.0f/65536.0f,3920.0f/65536.0f,3136.0f/65536.0f,1568.0f/65536.0f,448.0f/65536.0f,56.0f/65536.0f},
    {28.0f/65536.0f,224.0f/65536.0f, 784.0f/65536.0f,1568.0f/65536.0f,1960.0f/65536.0f,1568.0f/65536.0f, 784.0f/65536.0f,224.0f/65536.0f,28.0f/65536.0f},
    {8.0f/65536.0f,  64.0f/65536.0f, 224.0f/65536.0f, 448.0f/65536.0f, 560.0f/65536.0f, 448.0f/65536.0f, 224.0f/65536.0f,  64.0f/65536.0f, 8.0f/65536.0f},
    {1.0f/65536.0f,   8.0f/65536.0f,  28.0f/65536.0f,  56.0f/65536.0f,  70.0f/65536.0f,  56.0f/65536.0f,  28.0f/65536.0f,   8.0f/65536.0f, 1.0f/65536.0f}
};

const float GAUSSIAN_KERNEL_11X11[11][11] = {
    {1.0f/1048576.0f,    10.0f/1048576.0f,    45.0f/1048576.0f,   120.0f/1048576.0f,   210.0f/1048576.0f,   252.0f/1048576.0f,   210.0f/1048576.0f,   120.0f/1048576.0f,    45.0f/1048576.0f,    10.0f/1048576.0f, 1.0f/1048576.0f},
    {10.0f/1048576.0f,  100.0f/1048576.0f,   450.0f/1048576.0f,  1200.0f/1048576.0f,  2100.0f/1048576.0f,  2520.0f/1048576.0f,  2100.0f/1048576.0f,  1200.0f/1048576.0f,   450.0f/1048576.0f,   100.0f/1048576.0f,10.0f/1048576.0f},
    {45.0f/1048576.0f,  450.0f/1048576.0f,  2025.0f/1048576.0f,  5400.0f/1048576.0f,  9450.0f/1048576.0f, 11340.0f/1048576.0f,  9450.0f/1048576.0f,  5400.0f/1048576.0f,  2025.0f/1048576.0f,   450.0f/1048576.0f,45.0f/1048576.0f},
    {120.0f/1048576.0f,1200.0f/1048576.0f,  5400.0f/1048576.0f, 14400.0f/1048576.0f, 25200.0f/1048576.0f, 30240.0f/1048576.0f, 25200.0f/1048576.0f, 14400.0f/1048576.0f,  5400.0f/1048576.0f,  1200.0f/1048576.0f,120.0f/1048576.0f},
    {210.0f/1048576.0f,2100.0f/1048576.0f,  9450.0f/1048576.0f, 25200.0f/1048576.0f, 44100.0f/1048576.0f, 52920.0f/1048576.0f, 44100.0f/1048576.0f, 25200.0f/1048576.0f,  9450.0f/1048576.0f,  2100.0f/1048576.0f,210.0f/1048576.0f},
    {252.0f/1048576.0f,2520.0f/1048576.0f, 11340.0f/1048576.0f, 30240.0f/1048576.0f, 52920.0f/1048576.0f, 63504.0f/1048576.0f, 52920.0f/1048576.0f, 30240.0f/1048576.0f, 11340.0f/1048576.0f,  2520.0f/1048576.0f,252.0f/1048576.0f},
    {210.0f/1048576.0f,2100.0f/1048576.0f,  9450.0f/1048576.0f, 25200.0f/1048576.0f, 44100.0f/1048576.0f, 52920.0f/1048576.0f, 44100.0f/1048576.0f, 25200.0f/1048576.0f,  9450.0f/1048576.0f,  2100.0f/1048576.0f,210.0f/1048576.0f},
    {120.0f/1048576.0f,1200.0f/1048576.0f,  5400.0f/1048576.0f, 14400.0f/1048576.0f, 25200.0f/1048576.0f, 30240.0f/1048576.0f, 25200.0f/1048576.0f, 14400.0f/1048576.0f,  5400.0f/1048576.0f,  1200.0f/1048576.0f,120.0f/1048576.0f},
    {45.0f/1048576.0f,  450.0f/1048576.0f,  2025.0f/1048576.0f,  5400.0f/1048576.0f,  9450.0f/1048576.0f, 11340.0f/1048576.0f,  9450.0f/1048576.0f,  5400.0f/1048576.0f,  2025.0f/1048576.0f,   450.0f/1048576.0f,45.0f/1048576.0f},
    {10.0f/1048576.0f,  100.0f/1048576.0f,   450.0f/1048576.0f,  1200.0f/1048576.0f,  2100.0f/1048576.0f,  2520.0f/1048576.0f,  2100.0f/1048576.0f,  1200.0f/1048576.0f,   450.0f/1048576.0f,   100.0f/1048576.0f,10.0f/1048576.0f},
    {1.0f/1048576.0f,    10.0f/1048576.0f,    45.0f/1048576.0f,   120.0f/1048576.0f,   210.0f/1048576.0f,   252.0f/1048576.0f,   210.0f/1048576.0f,   120.0f/1048576.0f,    45.0f/1048576.0f,    10.0f/1048576.0f, 1.0f/1048576.0f}
};

inline unsigned char clamp_value(float value) {
    return (unsigned char) std::max(0, std::min(255, (int)std::round(value)));
}

#if defined(__GNUC__) || defined(__clang__)
#define CONVOLUTION_ALWAYS_INLINE inline __attribute__((always_inline))
#elif defined(_MSC_VER)
#define CONVOLUTION_ALWAYS_INLINE __forceinline
#else
#define CONVOLUTION_ALWAYS_INLINE inline
#endif

// =====================================================================
// FUNÇÕES DE APLICAÇÃO DE PIXEL (MANTIDAS INTACTAS)
// =====================================================================

static CONVOLUTION_ALWAYS_INLINE void apply_3_by_3_convolution_to_pixel(
    const ImageState& img, int x, int y, const float kernel[3][3],
    bool clamp_offset, bool single_channel, unsigned char* destination) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -1; k <= 1; ++k) {
            for (int l = -1; l <= 1; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[1 + k][1 + l] * img.data[source_index];
            }
        }
        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = destination[1] = destination[2] = value;
        return;
    }
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f;
    for (int k = -1; k <= 1; ++k) {
        for (int l = -1; l <= 1; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = kernel[1 + k][1 + l];
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    const float offset = clamp_offset ? 127.0f : 0.0f;
    destination[0] = clamp_value(sum_r + offset);
    destination[1] = clamp_value(sum_g + offset);
    destination[2] = clamp_value(sum_b + offset);
}

static CONVOLUTION_ALWAYS_INLINE void apply_5_by_5_convolution_to_pixel(
    const ImageState& img, int x, int y, const float kernel[5][5],
    bool clamp_offset, bool single_channel, unsigned char* destination) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -2; k <= 2; ++k) {
            for (int l = -2; l <= 2; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[2 + k][2 + l] * img.data[source_index];
            }
        }
        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = destination[1] = destination[2] = value;
        return;
    }
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f;
    for (int k = -2; k <= 2; ++k) {
        for (int l = -2; l <= 2; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = kernel[2 + k][2 + l];
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    const float offset = clamp_offset ? 127.0f : 0.0f;
    destination[0] = clamp_value(sum_r + offset);
    destination[1] = clamp_value(sum_g + offset);
    destination[2] = clamp_value(sum_b + offset);
}

static CONVOLUTION_ALWAYS_INLINE void apply_7_by_7_convolution_to_pixel(
    const ImageState& img, int x, int y, const float kernel[7][7],
    bool clamp_offset, bool single_channel, unsigned char* destination) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -3; k <= 3; ++k) {
            for (int l = -3; l <= 3; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[3 + k][3 + l] * img.data[source_index];
            }
        }
        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = destination[1] = destination[2] = value;
        return;
    }
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f;
    for (int k = -3; k <= 3; ++k) {
        for (int l = -3; l <= 3; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = kernel[3 + k][3 + l];
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    const float offset = clamp_offset ? 127.0f : 0.0f;
    destination[0] = clamp_value(sum_r + offset);
    destination[1] = clamp_value(sum_g + offset);
    destination[2] = clamp_value(sum_b + offset);
}

static CONVOLUTION_ALWAYS_INLINE void apply_9_by_9_convolution_to_pixel(
    const ImageState& img, int x, int y, const float kernel[9][9],
    bool clamp_offset, bool single_channel, unsigned char* destination) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -4; k <= 4; ++k) {
            for (int l = -4; l <= 4; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[4 + k][4 + l] * img.data[source_index];
            }
        }
        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = destination[1] = destination[2] = value;
        return;
    }
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f;
    for (int k = -4; k <= 4; ++k) {
        for (int l = -4; l <= 4; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = kernel[4 + k][4 + l];
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    const float offset = clamp_offset ? 127.0f : 0.0f;
    destination[0] = clamp_value(sum_r + offset);
    destination[1] = clamp_value(sum_g + offset);
    destination[2] = clamp_value(sum_b + offset);
}

static CONVOLUTION_ALWAYS_INLINE void apply_11_by_11_convolution_to_pixel(
    const ImageState& img, int x, int y, const float kernel[11][11],
    bool clamp_offset, bool single_channel, unsigned char* destination) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -5; k <= 5; ++k) {
            for (int l = -5; l <= 5; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[5 + k][5 + l] * img.data[source_index];
            }
        }
        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = destination[1] = destination[2] = value;
        return;
    }
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f;
    for (int k = -5; k <= 5; ++k) {
        for (int l = -5; l <= 5; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = kernel[5 + k][5 + l];
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    const float offset = clamp_offset ? 127.0f : 0.0f;
    destination[0] = clamp_value(sum_r + offset);
    destination[1] = clamp_value(sum_g + offset);
    destination[2] = clamp_value(sum_b + offset);
}

static CONVOLUTION_ALWAYS_INLINE void apply_gaussian_3_by_3_to_border_pixel(
    const ImageState& img, int x, int y, unsigned char* destination) {
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f, weight_sum = 0.0f;
    const int first_k = std::max(-1, y - (img.height - 1));
    const int last_k = std::min(1, y);
    const int first_l = std::max(-1, x - (img.width - 1));
    const int last_l = std::min(1, x);
    for (int k = first_k; k <= last_k; ++k) {
        for (int l = first_l; l <= last_l; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = GAUSSIAN_KERNEL_3X3[1 + k][1 + l];
            weight_sum += weight;
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    destination[0] = clamp_value(sum_r / weight_sum);
    destination[1] = clamp_value(sum_g / weight_sum);
    destination[2] = clamp_value(sum_b / weight_sum);
}

static CONVOLUTION_ALWAYS_INLINE void apply_gaussian_5_by_5_to_border_pixel(
    const ImageState& img, int x, int y, unsigned char* destination) {
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f, weight_sum = 0.0f;
    const int first_k = std::max(-2, y - (img.height - 1));
    const int last_k = std::min(2, y);
    const int first_l = std::max(-2, x - (img.width - 1));
    const int last_l = std::min(2, x);
    for (int k = first_k; k <= last_k; ++k) {
        for (int l = first_l; l <= last_l; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = GAUSSIAN_KERNEL_5X5[2 + k][2 + l];
            weight_sum += weight;
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    destination[0] = clamp_value(sum_r / weight_sum);
    destination[1] = clamp_value(sum_g / weight_sum);
    destination[2] = clamp_value(sum_b / weight_sum);
}

static CONVOLUTION_ALWAYS_INLINE void apply_gaussian_7_by_7_to_border_pixel(
    const ImageState& img, int x, int y, unsigned char* destination) {
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f, weight_sum = 0.0f;
    const int first_k = std::max(-3, y - (img.height - 1));
    const int last_k = std::min(3, y);
    const int first_l = std::max(-3, x - (img.width - 1));
    const int last_l = std::min(3, x);
    for (int k = first_k; k <= last_k; ++k) {
        for (int l = first_l; l <= last_l; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = GAUSSIAN_KERNEL_7X7[3 + k][3 + l];
            weight_sum += weight;
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    destination[0] = clamp_value(sum_r / weight_sum);
    destination[1] = clamp_value(sum_g / weight_sum);
    destination[2] = clamp_value(sum_b / weight_sum);
}

static CONVOLUTION_ALWAYS_INLINE void apply_gaussian_9_by_9_to_border_pixel(
    const ImageState& img, int x, int y, unsigned char* destination) {
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f, weight_sum = 0.0f;
    const int first_k = std::max(-4, y - (img.height - 1));
    const int last_k = std::min(4, y);
    const int first_l = std::max(-4, x - (img.width - 1));
    const int last_l = std::min(4, x);
    for (int k = first_k; k <= last_k; ++k) {
        for (int l = first_l; l <= last_l; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = GAUSSIAN_KERNEL_9X9[4 + k][4 + l];
            weight_sum += weight;
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    destination[0] = clamp_value(sum_r / weight_sum);
    destination[1] = clamp_value(sum_g / weight_sum);
    destination[2] = clamp_value(sum_b / weight_sum);
}

static CONVOLUTION_ALWAYS_INLINE void apply_gaussian_11_by_11_to_border_pixel(
    const ImageState& img, int x, int y, unsigned char* destination) {
    float sum_r = 0.0f, sum_g = 0.0f, sum_b = 0.0f, weight_sum = 0.0f;
    const int first_k = std::max(-5, y - (img.height - 1));
    const int last_k = std::min(5, y);
    const int first_l = std::max(-5, x - (img.width - 1));
    const int last_l = std::min(5, x);
    for (int k = first_k; k <= last_k; ++k) {
        for (int l = first_l; l <= last_l; ++l) {
            const int source_index = ((y - k) * img.width + (x - l)) * 3;
            const float weight = GAUSSIAN_KERNEL_11X11[5 + k][5 + l];
            weight_sum += weight;
            sum_r += weight * img.data[source_index];
            sum_g += weight * img.data[source_index + 1];
            sum_b += weight * img.data[source_index + 2];
        }
    }
    destination[0] = clamp_value(sum_r / weight_sum);
    destination[1] = clamp_value(sum_g / weight_sum);
    destination[2] = clamp_value(sum_b / weight_sum);
}

static CONVOLUTION_ALWAYS_INLINE int sobel_vertical_average(
    const ImageState& image, int x, int y, int channel) {
    int weighted_sum = 0, weight_sum = 0;
    for (int offset = -1; offset <= 1; ++offset) {
        const int sample_y = y + offset;
        if (sample_y < 0 || sample_y >= image.height) continue;
        const int weight = offset == 0 ? 2 : 1;
        weighted_sum += weight * image.data[(sample_y * image.width + x) * 3 + channel];
        weight_sum += weight;
    }
    return (weighted_sum + weight_sum / 2) / weight_sum;
}

static CONVOLUTION_ALWAYS_INLINE int sobel_horizontal_average(
    const ImageState& image, int x, int y, int channel) {
    int weighted_sum = 0, weight_sum = 0;
    for (int offset = -1; offset <= 1; ++offset) {
        const int sample_x = x + offset;
        if (sample_x < 0 || sample_x >= image.width) continue;
        const int weight = offset == 0 ? 2 : 1;
        weighted_sum += weight * image.data[(y * image.width + sample_x) * 3 + channel];
        weight_sum += weight;
    }
    return (weighted_sum + weight_sum / 2) / weight_sum;
}

static CONVOLUTION_ALWAYS_INLINE unsigned char compute_sobel_detail_at_pixel(
    const ImageState& image, int x, int y) {
    const int left_x = x > 0 ? x - 1 : x;
    const int right_x = x + 1 < image.width ? x + 1 : x;
    const int top_y = y > 0 ? y - 1 : y;
    const int bottom_y = y + 1 < image.height ? y + 1 : y;

    int detail = 0;
    for (int channel = 0; channel < 3; ++channel) {
        const int left = sobel_vertical_average(image, left_x, y, channel);
        const int right = sobel_vertical_average(image, right_x, y, channel);
        const int top = sobel_horizontal_average(image, x, top_y, channel);
        const int bottom = sobel_horizontal_average(image, x, bottom_y, channel);

        const int gradient_x = std::abs(right - left);
        const int gradient_y = std::abs(bottom - top);
        const int larger = std::max(gradient_x, gradient_y);
        const int smaller = std::min(gradient_x, gradient_y);
        detail = std::max(detail, std::min(255, larger + smaller / 2));
    }
    return static_cast<unsigned char>(detail);
}

#undef CONVOLUTION_ALWAYS_INLINE

// =====================================================================
// OPERAÇÕES PARALELIZADAS COM OPENMP
// =====================================================================

bool apply_3_by_3_convolution(ImageState& img, const float kernel[3][3], bool clamp_offset, bool single_channel) {
    if (img.width < 3 || img.height < 3) {
        fprintf(stderr, "Imagem muito pequena para realizar operação de convolução 3x3!\n");
        return false;
    }
    const int new_width = img.width - 2;
    const int new_height = img.height - 2;
    unsigned char* new_img_data = (unsigned char*) malloc(static_cast<size_t>(new_width) * new_height * 3);
    if (!new_img_data) return false;

    #pragma omp parallel for schedule(static)
    for (int j = 1; j < img.height - 1; ++j) {
        for (int i = 1; i < img.width - 1; ++i) {
            unsigned char* destination = new_img_data + ((j - 1) * new_width + (i - 1)) * 3;
            apply_3_by_3_convolution_to_pixel(img, i, j, kernel, clamp_offset, single_channel, destination);
        }
    }
    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_5_by_5_convolution(ImageState& img, const float kernel[5][5], bool clamp_offset, bool single_channel) {
    if (img.width < 5 || img.height < 5) return false;
    const int new_width = img.width - 4;
    const int new_height = img.height - 4;
    unsigned char* new_img_data = (unsigned char*) malloc(static_cast<size_t>(new_width) * new_height * 3);
    if (!new_img_data) return false;

    #pragma omp parallel for schedule(static)
    for (int j = 2; j < img.height - 2; ++j) {
        for (int i = 2; i < img.width - 2; ++i) {
            unsigned char* destination = new_img_data + ((j - 2) * new_width + (i - 2)) * 3;
            apply_5_by_5_convolution_to_pixel(img, i, j, kernel, clamp_offset, single_channel, destination);
        }
    }
    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_7_by_7_convolution(ImageState& img, const float kernel[7][7], bool clamp_offset, bool single_channel) {
    if (img.width < 7 || img.height < 7) return false;
    const int new_width = img.width - 6;
    const int new_height = img.height - 6;
    unsigned char* new_img_data = (unsigned char*) malloc(static_cast<size_t>(new_width) * new_height * 3);
    if (!new_img_data) return false;

    #pragma omp parallel for schedule(static)
    for (int j = 3; j < img.height - 3; ++j) {
        for (int i = 3; i < img.width - 3; ++i) {
            unsigned char* destination = new_img_data + ((j - 3) * new_width + (i - 3)) * 3;
            apply_7_by_7_convolution_to_pixel(img, i, j, kernel, clamp_offset, single_channel, destination);
        }
    }
    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_9_by_9_convolution(ImageState& img, const float kernel[9][9], bool clamp_offset, bool single_channel) {
    if (img.width < 9 || img.height < 9) return false;
    const int new_width = img.width - 8;
    const int new_height = img.height - 8;
    unsigned char* new_img_data = (unsigned char*) malloc(static_cast<size_t>(new_width) * new_height * 3);
    if (!new_img_data) return false;

    #pragma omp parallel for schedule(static)
    for (int j = 4; j < img.height - 4; ++j) {
        for (int i = 4; i < img.width - 4; ++i) {
            unsigned char* destination = new_img_data + ((j - 4) * new_width + (i - 4)) * 3;
            apply_9_by_9_convolution_to_pixel(img, i, j, kernel, clamp_offset, single_channel, destination);
        }
    }
    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_11_by_11_convolution(ImageState& img, const float kernel[11][11], bool clamp_offset, bool single_channel) {
    if (img.width < 11 || img.height < 11) return false;
    const int new_width = img.width - 10;
    const int new_height = img.height - 10;
    unsigned char* new_img_data = (unsigned char*) malloc(static_cast<size_t>(new_width) * new_height * 3);
    if (!new_img_data) return false;

    #pragma omp parallel for schedule(static)
    for (int j = 5; j < img.height - 5; ++j) {
        for (int i = 5; i < img.width - 5; ++i) {
            unsigned char* destination = new_img_data + ((j - 5) * new_width + (i - 5)) * 3;
            apply_11_by_11_convolution_to_pixel(img, i, j, kernel, clamp_offset, single_channel, destination);
        }
    }
    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

static bool get_safe_pixel_count(const ImageState& image, size_t& pixel_count) {
    if (!image.data || image.width <= 0 || image.height <= 0) return false;
    const size_t width = static_cast<size_t>(image.width);
    const size_t height = static_cast<size_t>(image.height);
    if (height > std::numeric_limits<size_t>::max() / width) return false;
    pixel_count = width * height;
    return pixel_count <= static_cast<size_t>(std::numeric_limits<int>::max()) / 3;
}

bool compute_sobel_detail_map(const ImageState& image, std::vector<unsigned char>& detail_map) {
    size_t pixel_count = 0;
    if (!get_safe_pixel_count(image, pixel_count) || pixel_count > detail_map.max_size()) return false;
    try {
        detail_map.assign(pixel_count, 0);
    } catch (const std::bad_alloc&) {
        return false;
    }

    #pragma omp parallel for schedule(static)
    for (int y = 0; y < image.height; ++y) {
        for (int x = 0; x < image.width; ++x) {
            detail_map[static_cast<size_t>(y) * image.width + x] = compute_sobel_detail_at_pixel(image, x, y);
        }
    }
    return true;
}

static unsigned char nearest_rank_percentile(const std::array<size_t, 256>& histogram, size_t value_count, unsigned int percentile) {
    const size_t target_rank = (value_count / 100) * percentile + ((value_count % 100) * percentile + 99) / 100;
    size_t cumulative_count = 0;
    for (size_t value = 0; value < histogram.size(); ++value) {
        cumulative_count += histogram[value];
        if (cumulative_count >= target_rank) return static_cast<unsigned char>(value);
    }
    return 255;
}

bool apply_varying_window_gaussian_denoising(ImageState& image) {
    size_t pixel_count = 0;
    if (!get_safe_pixel_count(image, pixel_count)) return false;

    std::vector<unsigned char> detail_map;
    if (!compute_sobel_detail_map(image, detail_map)) return false;

    std::array<size_t, 256> histogram{};
    for (unsigned char detail : detail_map) {
        ++histogram[detail];
    }

    const unsigned char percentile_20 = nearest_rank_percentile(histogram, pixel_count, 20);
    const unsigned char percentile_40 = nearest_rank_percentile(histogram, pixel_count, 40);
    const unsigned char percentile_60 = nearest_rank_percentile(histogram, pixel_count, 60);
    const unsigned char percentile_80 = nearest_rank_percentile(histogram, pixel_count, 80);

    unsigned char* new_image_data = static_cast<unsigned char*>(malloc(pixel_count * 3));
    if (!new_image_data) return false;

    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < image.height; ++y) {
        for (int x = 0; x < image.width; ++x) {
            const size_t pixel_index = static_cast<size_t>(y) * image.width + x;
            unsigned char* destination = new_image_data + pixel_index * 3;
            const unsigned char detail = detail_map[pixel_index];

            int kernel_size;
            if (detail <= percentile_20) kernel_size = 11;
            else if (detail <= percentile_40) kernel_size = 9;
            else if (detail <= percentile_60) kernel_size = 7;
            else if (detail <= percentile_80) kernel_size = 5;
            else kernel_size = 3;

            const int radius = kernel_size / 2;
            const bool kernel_fits = x >= radius && x < image.width - radius && y >= radius && y < image.height - radius;

            switch (kernel_size) {
                case 3:
                    if (kernel_fits) apply_3_by_3_convolution_to_pixel(image, x, y, GAUSSIAN_KERNEL_3X3, false, false, destination);
                    else apply_gaussian_3_by_3_to_border_pixel(image, x, y, destination);
                    break;
                case 5:
                    if (kernel_fits) apply_5_by_5_convolution_to_pixel(image, x, y, GAUSSIAN_KERNEL_5X5, false, false, destination);
                    else apply_gaussian_5_by_5_to_border_pixel(image, x, y, destination);
                    break;
                case 7:
                    if (kernel_fits) apply_7_by_7_convolution_to_pixel(image, x, y, GAUSSIAN_KERNEL_7X7, false, false, destination);
                    else apply_gaussian_7_by_7_to_border_pixel(image, x, y, destination);
                    break;
                case 9:
                    if (kernel_fits) apply_9_by_9_convolution_to_pixel(image, x, y, GAUSSIAN_KERNEL_9X9, false, false, destination);
                    else apply_gaussian_9_by_9_to_border_pixel(image, x, y, destination);
                    break;
                case 11:
                    if (kernel_fits) apply_11_by_11_convolution_to_pixel(image, x, y, GAUSSIAN_KERNEL_11X11, false, false, destination);
                    else apply_gaussian_11_by_11_to_border_pixel(image, x, y, destination);
                    break;
            }
        }
    }
    free(image.data);
    image.data = new_image_data;
    return true;
}

void rotate_90_degrees_clockwise(ImageState& img){
    int new_img_height = img.width;
    int new_img_width = img.height;
    unsigned char* new_data = (unsigned char*) malloc(new_img_height * new_img_width * 3);

    #pragma omp parallel for schedule(static)
    for(int j = 0; j < img.height; j++){
        for(int i = 0; i < img.width; i++){
            int old_index = (j * img.width + i) * 3;
            int new_index = ((img.width - 1 - i) * new_img_width + j) * 3;
            memcpy(new_data + new_index, img.data + old_index, 3);
        }
    }
    free(img.data);
    img.data = new_data;
    img.width = new_img_width;
    img.height = new_img_height;
}

void rotate_90_degrees_counterclockwise(ImageState& img){
    int new_img_height = img.width;
    int new_img_width = img.height;
    unsigned char* new_data = (unsigned char*) malloc(new_img_height * new_img_width * 3);

    #pragma omp parallel for schedule(static)
    for(int j = 0; j < img.height; j++){
        for(int i = 0; i < img.width; i++){
            int old_index = (j * img.width + i) * 3;
            int new_index = (i * new_img_width + (img.height - 1 - j)) * 3;
            memcpy(new_data + new_index, img.data + old_index, 3);
        }
    }
    free(img.data);
    img.data = new_data;
    img.width = new_img_width;
    img.height = new_img_height;
}

void zoom_in_image(ImageState& img){
    long long h = 1LL * img.height * 2 - 1;
    long long w  = 1LL * img.width * 2 - 1;
    if(h > INT_MAX || w > INT_MAX || h * w * 3LL > INT_MAX) return;

    int new_height = (int) h;
    int new_width = (int) w;
    unsigned char* new_data = (unsigned char*) malloc(new_width * new_height * 3);

    #pragma omp parallel for schedule(static)
    for(int j = 0; j < img.height; j++){
        for(int i = 0; i < img.width; i++){
            int old_index = (j * img.width + i) * 3;
            int new_index = (j * 2 * new_width + i * 2) * 3;
            memcpy(new_data + new_index, img.data + old_index, 3);
        }
    }

    #pragma omp parallel for schedule(static)
    for(int j = 0; j < new_height; j += 2){
        for(int i = 1; i < new_width; i += 2){
            int index = (j * new_width + i) * 3;
            new_data[index] = (unsigned char) ((new_data[index - 3] + new_data[index + 3]) / 2);
            new_data[index + 1] = (unsigned char) ((new_data[index - 3 + 1] + new_data[index + 3 + 1]) / 2);
            new_data[index + 2] = (unsigned char) ((new_data[index - 3 + 2] + new_data[index + 3 + 2]) / 2);
        }
    }

    #pragma omp parallel for schedule(static)
    for(int j = 1; j < new_height; j += 2){
        for(int i = 0; i < new_width; i++){
            int index = (j * new_width + i) * 3;
            new_data[index] = (unsigned char) ((new_data[index - new_width * 3] + new_data[index + new_width * 3]) / 2);
            new_data[index + 1] = (unsigned char) ((new_data[index - new_width * 3 + 1] + new_data[index + new_width * 3 + 1]) / 2);
            new_data[index + 2] = (unsigned char) ((new_data[index - new_width * 3 + 2] + new_data[index + new_width * 3 + 2]) / 2);
        }
    }
    free(img.data);
    img.data = new_data;
    img.width = new_width;
    img.height = new_height;
}

void zoom_out_image(ImageState& img, Rectangle& rec){
    int new_height = ceil((float) img.height / rec.height);
    int new_width = ceil((float) img.width / rec.width);
    unsigned char* new_data = (unsigned char*) malloc(new_width * new_height * 3);

    #pragma omp parallel for schedule(static)
    for(int j = 0; j < new_height; j++){
        // Armadilha Corrigida: a variável `avg` precisa ser declarada DENTRO do loop 
        // para que cada thread tenha a sua, evitando condição de corrida!
        unsigned char avg[3];
        for(int i = 0; i < new_width; i++){
            compute_rgb_avg_on_rectangle(avg, i * rec.width, j * rec.height, rec.width, rec.height, img);
            int index = (j * new_width + i) * 3;
            new_data[index] = avg[0];
            new_data[index + 1] = avg[1];
            new_data[index + 2] = avg[2];
        }
    }
    free(img.data);
    img.data = new_data;
    img.width = new_width;
    img.height = new_height;
}

void compute_rgb_avg_on_rectangle(unsigned char avg[3], int rec_x, int rec_y, int rec_width, int rec_height, ImageState& img){
    unsigned long long sum_r = 0, sum_g = 0, sum_b = 0;
    int num_pixels = 0;
    for(int j = rec_y; j < rec_y + rec_height; j++){
        if(j >= img.height) break;
        for(int i = rec_x; i < rec_x + rec_width; i++){
            if(i >= img.width) break;
            int index = (j * img.width + i) * 3;
            sum_r += img.data[index];
            sum_g += img.data[index + 1];
            sum_b += img.data[index + 2];
            num_pixels++;
        }
    }
    avg[0] = (unsigned char) (sum_r / num_pixels);
    avg[1] = (unsigned char) (sum_g / num_pixels);
    avg[2] = (unsigned char) (sum_b / num_pixels);
}

void histogram_matching(ImageState& src_img, ImageState& target_img){
    unsigned int src_hist[256];
    unsigned int target_hist[256];
    compute_normalized_cummulative_histogram(src_img, src_hist);
    compute_normalized_cummulative_histogram(target_img, target_hist);

    // O array tem 256 posições, overhead grande para paralelizar, manter sequencial
    for(int i = 0; i < 256; i++)
        src_hist[i] = find_shade_level_closest_to(src_hist[i], target_hist);

    #pragma omp parallel for schedule(static)
    for(int i = 0; i < src_img.height; i++){
        for(int j = 0; j < src_img.width; j++){
            int index = (i * src_img.width + j) * 3;
            for(int channel = 0; channel < 3; channel++){
                unsigned char old_value = src_img.data[index + channel];
                src_img.data[index + channel] = src_hist[old_value]; 
            }
        }
    }
}

unsigned char find_shade_level_closest_to(int value, unsigned int target_hist[256]) {
    auto pointer_to_closest_value = std::lower_bound(target_hist, target_hist + 256, value);
    if(pointer_to_closest_value == target_hist) return 0;
    int idx = pointer_to_closest_value - target_hist;
    if (std::abs((int)target_hist[idx] - value) < std::abs((int)target_hist[idx - 1] - value))
        return (unsigned char) idx;
    else
        return (unsigned char) (idx - 1);
}

void equalize_histogram(ImageState& img, unsigned int cummulative_hist[256]){
    compute_normalized_cummulative_histogram(img, cummulative_hist);
    
    #pragma omp parallel for schedule(static)
    for(int i = 0; i < img.height; i++){
        for(int j = 0; j < img.width; j++){
            int index = (i * img.width + j) * 3;
            for(int channel = 0; channel < 3; channel++){
                img.data[index + channel] = (unsigned char) cummulative_hist[img.data[index + channel]];
            }
        }
    }
}

void compute_normalized_cummulative_histogram(ImageState& img, unsigned int hist[256]){
    compute_histogram(img, hist, false);
    float normalize_factor = 255.0f / (img.width * img.height);
    // Este loop é INQUEBRÁVEL (dependência iterativa). DEVE ser sequencial!
    for(int i = 1; i < 256; i++){
        hist[i] = hist[i - 1] + hist[i];
    }
    for(int i = 0; i < 256; i++){
        hist[i] = std::round(hist[i] * normalize_factor);
    }
}

void apply_negative(ImageState& img){
    #pragma omp parallel for schedule(static)
    for(int i = 0; i < img.height; i++){
        for(int j = 0; j < img.width; j++){
            int index = (i * img.width + j) * 3;
            for(int channel = 0; channel < 3; channel++){
                img.data[index + channel] = 255 - img.data[index + channel];
            }
        }
    }
}

void adjust_contrast(ImageState& img, float contrast_factor){
    if(contrast_factor == 1.0f) return;

    #pragma omp parallel for schedule(static)
    for(int i = 0; i < img.height; i++){
        for(int j = 0; j < img.width; j++){
            int index = (i * img.width + j) * 3;
            for(int channel = 0; channel < 3; channel++){
                float value = img.data[index + channel] * contrast_factor;
                int clamped = std::clamp(static_cast<int>(value), 0, 255);
                img.data[index + channel] = static_cast<unsigned char>(clamped);
            }
        }
    }
}

void compute_histogram(ImageState& img,  unsigned int hist[256], bool convert_to_gray_scale){
    for(int i = 0; i < 256; i++){
        hist[i] = 0;
    }

    if(!img.isGrayScale){
        if(convert_to_gray_scale)
            apply_gray_scale_inplace(img);
        else{
            #pragma omp parallel for schedule(static) reduction(+:hist[:256])
            for (int j = 0; j < img.height; j++) {
                for (int i = 0; i < img.width; i++) {
                    int index = (j * img.width + i) * 3;
                    unsigned char r = img.data[index];
                    unsigned char g = img.data[index + 1];
                    unsigned char b = img.data[index + 2];
                    unsigned char gray = (unsigned char)(0.299 * r + 0.587 * g + 0.114 * b);
                    hist[gray] += 1; 
                }
            }
            return;
        }
    }
    
    #pragma omp parallel for schedule(static) reduction(+:hist[:256])
    for(int i = 0; i < img.height; i++){
        for(int j = 0; j < img.width; j++){
            int index = (i * img.width + j) * 3;
            hist[img.data[index]] += 1; 
        }
    }
}

void save_image(ImageState& img, const char* filename) {
    stbi_write_jpg(filename, img.width, img.height, 3, img.data, 90);
    printf("Imagem salva como %s\n", filename);
}

bool load_image(const char* filename, ImageState& img) {
    int width, height, channels;
    unsigned char* pixels = stbi_load(filename, &width, &height, &channels, 3);
    if (!pixels) return false;

    img.width = width;
    img.height = height;
    img.isGrayScale = false;
    img.data = (unsigned char*) malloc(width * height * 3);
    if (!img.data) {
        stbi_image_free(pixels);
        return false;
    }
    memcpy(img.data, pixels, width * height * 3);
    stbi_image_free(pixels); 
    return true;
}

void apply_gray_scale_inplace(ImageState& img) {
    if(img.isGrayScale) return;

    #pragma omp parallel for schedule(static)
    for (int j = 0; j < img.height; j++) {
        for (int i = 0; i < img.width; i++) {
            int index = (j * img.width + i) * 3;
            unsigned char r = img.data[index];
            unsigned char g = img.data[index + 1];
            unsigned char b = img.data[index + 2];
            unsigned char gray = (unsigned char)(0.299 * r + 0.587 * g + 0.114 * b);
            img.data[index] = img.data[index + 1] = img.data[index + 2] = gray;
        }
    } 
    img.isGrayScale = true;
}

void adjust_brightness(ImageState& img, int adjust_value){
    if(adjust_value == 0) return;

    #pragma omp parallel for schedule(static)
    for(int i = 0; i < img.height; i++){
        for(int j = 0; j < img.width; j++){
            int index = (i * img.width + j) * 3;
            for(int channel = 0; channel < 3; channel++)
                img.data[index + channel] = std::clamp(img.data[index + channel] + adjust_value, 0, 255);
        }
    }
}

void flip_horizontal(ImageState& img) {
    int width = img.width;
    int height = img.height;

    #pragma omp parallel for schedule(static)
    for (int j = 0; j < height; j++) {
        // Armadilha Corrigida: o buffer precisa ser local para não cruzar pixels das threads
        unsigned char pixel_buffer[3]; 
        for (int i = 0; i < width / 2; i++) {
            memcpy(pixel_buffer, img.data + (j * width + i) * 3, 3);
            memcpy(img.data + (j * width + i) * 3,
                   img.data + (j * width + (width - 1 - i)) * 3, 3);
            memcpy(img.data + (j * width + (width - 1 - i)) * 3, pixel_buffer, 3);
        }
    }
}

void flip_vertical(ImageState& img){
    int width = img.width;
    int height = img.height;

    // Armadilha Corrigida: Área paralela cria um buffer de linha privativo por Thread
    #pragma omp parallel
    {
        unsigned char *row_buffer = (unsigned char*) malloc(width * 3);
        
        #pragma omp for schedule(static)
        for(int j = 0; j < height / 2; j++){
            memcpy(row_buffer, img.data + j * width * 3, width * 3);
            memcpy(img.data + j * width * 3, img.data + (height - 1 - j) * width * 3, width * 3);
            memcpy(img.data + (height - 1 - j) * width * 3, row_buffer, width * 3);
        }
        
        free(row_buffer);
    }
} 

std::array<unsigned char, 2> find_min_and_max_luminance_on_gray_scale_image(int width, int height, unsigned char* data){
    // Armadilha Corrigida: Variáveis promovidas a int temporariamente para as reduções de min/max operarem seguramente
    int local_min = 255;
    int local_max = 0;

    #pragma omp parallel for schedule(static) reduction(min:local_min) reduction(max:local_max)
    for(int j = 0; j < height; j++){
        for(int i = 0; i < width; i++){
            int index = (j * width + i) * 3;
            int luminance = data[index];

            if(luminance < local_min) local_min = luminance;
            if(luminance > local_max) local_max = luminance;
        }
    }
    return {(unsigned char)local_min, (unsigned char)local_max};
}
    
void quantize_gray(ImageState& img, int levels) {
    if(!img.isGrayScale) apply_gray_scale_inplace(img);

    std::array<unsigned char, 2> min_and_max_l = find_min_and_max_luminance_on_gray_scale_image(img.width, img.height, img.data);
    unsigned char min_l = min_and_max_l[0];
    unsigned char max_l = min_and_max_l[1];
    int num_levels = max_l - min_l + 1;

    if (num_levels <= levels) return;
    float tb = (float) num_levels / levels;

    #pragma omp parallel for schedule(static)
    for (int j = 0; j < img.height; j++) {
        for (int i = 0; i < img.width; i++) {
                int index = (j * img.width + i) * 3;
                unsigned char luminance = img.data[index]; 
                int new_luminance_bin = (int) ((luminance - min_l + 0.5) / tb); 
                unsigned char new_luminance = (unsigned char) round(min_l - 0.5 + (new_luminance_bin + 0.5) * tb);

                img.data[index] = new_luminance;
                img.data[index + 1] = new_luminance;
                img.data[index + 2] = new_luminance;
        }
    }
}

void reset(ImageState& img, unsigned char* original_data, int original_width, int original_height) {
    if (original_data) {
        free(img.data);
        img.data = (unsigned char*) malloc(original_width * original_height * 3);
        memcpy(img.data, original_data, original_width * original_height * 3);
        img.width = original_width;
        img.height = original_height;
        img.isGrayScale = false;
    }
    else {
        printf("ERRO CRÍTICO: sem imagem original para resetar!\n");
    }
}