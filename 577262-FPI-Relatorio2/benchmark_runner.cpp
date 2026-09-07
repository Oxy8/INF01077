#include "image_manipulation.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <system_error>
#include <vector>

namespace fs = std::filesystem;

// Parâmetros usados pelas transformações configuráveis.
#define BENCHMARK_BRIGHTNESS_ADJUSTMENT 127
#define BENCHMARK_CONTRAST_FACTOR 1.5f
#define BENCHMARK_QUANTIZATION_LEVELS 16
#define BENCHMARK_ZOOM_OUT_WIDTH 2
#define BENCHMARK_ZOOM_OUT_HEIGHT 2
#define BENCHMARK_CONVOLUTION_CLAMP_OFFSET false
#define BENCHMARK_CONVOLUTION_SINGLE_CHANNEL false

using Transformation = bool (*)(ImageState&);

bool transform_grayscale(ImageState& image) {
    apply_gray_scale_inplace(image);
    return true;
}

bool transform_flip_horizontal(ImageState& image) {
    flip_horizontal(image);
    return true;
}

bool transform_adjust_brightness(ImageState& image) {
    adjust_brightness(image, BENCHMARK_BRIGHTNESS_ADJUSTMENT);
    return true;
}

bool transform_flip_vertical(ImageState& image) {
    flip_vertical(image);
    return true;
}

bool transform_quantize(ImageState& image) {
    quantize_gray(image, BENCHMARK_QUANTIZATION_LEVELS);
    return true;
}

bool transform_adjust_contrast(ImageState& image) {
    adjust_contrast(image, BENCHMARK_CONTRAST_FACTOR);
    return true;
}

bool transform_negative(ImageState& image) {
    apply_negative(image);
    return true;
}

bool transform_equalize_histogram(ImageState& image) {
    unsigned int cumulative_histogram[256];
    equalize_histogram(image, cumulative_histogram);
    return true;
}

bool transform_zoom_in(ImageState& image) {
    zoom_in_image(image);
    return true;
}

bool transform_zoom_out(ImageState& image) {
    Rectangle rectangle{
        0,
        0,
        BENCHMARK_ZOOM_OUT_WIDTH,
        BENCHMARK_ZOOM_OUT_HEIGHT
    };
    zoom_out_image(image, rectangle);
    return true;
}

bool transform_rotate_clockwise(ImageState& image) {
    rotate_90_degrees_clockwise(image);
    return true;
}

bool transform_rotate_counterclockwise(ImageState& image) {
    rotate_90_degrees_counterclockwise(image);
    return true;
}

bool transform_gaussian_convolution_3x3(ImageState& image) {
    return apply_3_by_3_convolution(
        image,
        GAUSSIAN_KERNEL_3X3,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_5x5(ImageState& image) {
    return apply_5_by_5_convolution(
        image,
        GAUSSIAN_KERNEL_5X5,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_7x7(ImageState& image) {
    return apply_7_by_7_convolution(
        image,
        GAUSSIAN_KERNEL_7X7,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_9x9(ImageState& image) {
    return apply_9_by_9_convolution(
        image,
        GAUSSIAN_KERNEL_9X9,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_11x11(ImageState& image) {
    return apply_11_by_11_convolution(
        image,
        GAUSSIAN_KERNEL_11X11,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_varying_window_gaussian_denoising(ImageState& image) {
    return apply_varying_window_gaussian_denoising(image);
}

// Nomes que podem ser usados para montar a lista abaixo.
#define TRANSFORM_GRAYSCALE transform_grayscale
#define TRANSFORM_FLIP_HORIZONTAL transform_flip_horizontal
#define TRANSFORM_ADJUST_BRIGHTNESS transform_adjust_brightness
#define TRANSFORM_FLIP_VERTICAL transform_flip_vertical
#define TRANSFORM_QUANTIZE transform_quantize
#define TRANSFORM_ADJUST_CONTRAST transform_adjust_contrast
#define TRANSFORM_NEGATIVE transform_negative
#define TRANSFORM_EQUALIZE_HISTOGRAM transform_equalize_histogram
#define TRANSFORM_ZOOM_IN transform_zoom_in
#define TRANSFORM_ZOOM_OUT transform_zoom_out
#define TRANSFORM_ROTATE_CLOCKWISE transform_rotate_clockwise
#define TRANSFORM_ROTATE_COUNTERCLOCKWISE transform_rotate_counterclockwise
#define TRANSFORM_GAUSSIAN_CONVOLUTION_3X3 transform_gaussian_convolution_3x3
#define TRANSFORM_GAUSSIAN_CONVOLUTION_5X5 transform_gaussian_convolution_5x5
#define TRANSFORM_GAUSSIAN_CONVOLUTION_7X7 transform_gaussian_convolution_7x7
#define TRANSFORM_GAUSSIAN_CONVOLUTION_9X9 transform_gaussian_convolution_9x9
#define TRANSFORM_GAUSSIAN_CONVOLUTION_11X11 transform_gaussian_convolution_11x11
#define TRANSFORM_VARYING_WINDOW_GAUSSIAN_DENOISING transform_varying_window_gaussian_denoising

// Edite esta lista para mudar quais transformações são executadas e a ordem.
static constexpr Transformation TRANSFORMATIONS[] = {
    TRANSFORM_GRAYSCALE,
    TRANSFORM_FLIP_HORIZONTAL,
    TRANSFORM_ADJUST_BRIGHTNESS,
    TRANSFORM_FLIP_VERTICAL,
    TRANSFORM_QUANTIZE,
    TRANSFORM_ADJUST_CONTRAST,
    TRANSFORM_NEGATIVE,
    TRANSFORM_EQUALIZE_HISTOGRAM,
    TRANSFORM_ZOOM_IN,
    TRANSFORM_ZOOM_OUT,
    TRANSFORM_ROTATE_CLOCKWISE,
    TRANSFORM_ROTATE_COUNTERCLOCKWISE,
    TRANSFORM_GAUSSIAN_CONVOLUTION_3X3,
    TRANSFORM_GAUSSIAN_CONVOLUTION_5X5,
    TRANSFORM_GAUSSIAN_CONVOLUTION_7X7,
    TRANSFORM_GAUSSIAN_CONVOLUTION_9X9,
    TRANSFORM_GAUSSIAN_CONVOLUTION_11X11,
    TRANSFORM_VARYING_WINDOW_GAUSSIAN_DENOISING,
};

bool has_supported_extension(const fs::path& path) {
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(),
        [](unsigned char character) {
            return static_cast<char>(std::tolower(character));
        });

    static const std::vector<std::string> supported_extensions = {
        ".jpg", ".jpeg", ".png", ".bmp", ".tga", ".gif",
        ".psd", ".hdr", ".pic", ".pnm", ".ppm", ".pgm"
    };

    return std::find(
        supported_extensions.begin(),
        supported_extensions.end(),
        extension
    ) != supported_extensions.end();
}

bool process_image(const fs::path& path) {
    ImageState image{};
    const std::string filename = path.string();

    if (!load_image(filename.c_str(), image)) {
        fprintf(stderr, "Erro ao carregar a imagem: %s\n", filename.c_str());
        return false;
    }

    for (Transformation transformation : TRANSFORMATIONS) {
        if (!transformation(image)) {
            fprintf(stderr, "Erro ao processar a imagem: %s\n", filename.c_str());
            free(image.data);
            return false;
        }
    }

    free(image.data);
    return true;
}

int process_folder(const fs::path& folder) {
    std::error_code error;
    if (!fs::is_directory(folder, error)) {
        fprintf(stderr, "Erro: pasta não encontrada: %s\n", folder.string().c_str());
        return 1;
    }

    std::vector<fs::path> images;
    fs::directory_iterator iterator(folder, error);
    fs::directory_iterator end;

    while (!error && iterator != end) {
        const fs::directory_entry& entry = *iterator;
        std::error_code entry_error;
        if (entry.is_regular_file(entry_error) && !entry_error && has_supported_extension(entry.path())) {
            images.push_back(entry.path());
        }
        iterator.increment(error);
    }

    if (error) {
        fprintf(stderr, "Erro ao percorrer a pasta: %s\n", folder.string().c_str());
        return 1;
    }

    std::sort(images.begin(), images.end());

    if (images.empty()) {
        fprintf(stderr, "Erro: nenhuma imagem suportada encontrada em: %s\n", folder.string().c_str());
        return 1;
    }

    bool all_succeeded = true;
    for (const fs::path& image : images) {
        if (!process_image(image)) {
            all_succeeded = false;
        }
    }

    return all_succeeded ? 0 : 1;
}

void print_usage(const char* executable) {
    fprintf(stderr, "Uso: %s --image CAMINHO | --folder CAMINHO\n", executable);
}

int main(int argc, char** argv) {
    if (argc != 3) {
        print_usage(argv[0]);
        return 2;
    }

    const std::string mode = argv[1];
    const fs::path path = argv[2];

    if (mode == "--image") {
        return process_image(path) ? 0 : 1;
    }

    if (mode == "--folder") {
        return process_folder(path);
    }

    print_usage(argv[0]);
    return 2;
}
