#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <random>
#include <string>
#include <vector>

namespace fs = std::filesystem;

struct Options {
    fs::path output = "images/controls";
    int width = 6000;
    int height = 6000;
    unsigned int seed = 577262;
};

void set_pixel(std::vector<unsigned char>& image, int width, int x, int y, unsigned char value) {
    const size_t index = (static_cast<size_t>(y) * width + x) * 3;
    image[index] = value;
    image[index + 1] = value;
    image[index + 2] = value;
}

bool write_image(const fs::path& path, const std::vector<unsigned char>& image, const Options& options) {
    if (!stbi_write_png(path.string().c_str(), options.width, options.height, 3, image.data(), options.width * 3)) {
        std::cerr << "Erro ao salvar " << path << "\n";
        return false;
    }
    std::cout << "Criado: " << path << "\n";
    return true;
}

std::string dimensions(const Options& options) {
    return std::to_string(options.width) + "x" + std::to_string(options.height) + ".png";
}

bool generate_smooth(const Options& options) {
    std::vector<unsigned char> image(static_cast<size_t>(options.width) * options.height * 3, 255);
    return write_image(options.output / ("control_smooth_" + dimensions(options)), image, options);
}

bool generate_noise(const Options& options) {
    std::vector<unsigned char> image(static_cast<size_t>(options.width) * options.height * 3);
    std::mt19937 generator(options.seed);
    std::uniform_int_distribution<int> distribution(0, 255);
    for (unsigned char& value : image) value = static_cast<unsigned char>(distribution(generator));
    return write_image(options.output / ("control_noise_" + dimensions(options)), image, options);
}

bool generate_half_noise(const Options& options) {
    std::vector<unsigned char> image(static_cast<size_t>(options.width) * options.height * 3);
    std::mt19937 generator(options.seed + 1);
    std::uniform_int_distribution<int> distribution(0, 255);
    for (int y = 0; y < options.height; ++y) {
        for (int x = 0; x < options.width; ++x) {
            const unsigned char value = y < options.height / 2 ? 255 : static_cast<unsigned char>(distribution(generator));
            set_pixel(image, options.width, x, y, value);
        }
    }
    return write_image(options.output / ("control_half_noise_" + dimensions(options)), image, options);
}

bool generate_bands(const Options& options) {
    constexpr int band_size = 256;
    std::vector<unsigned char> image(static_cast<size_t>(options.width) * options.height * 3);
    std::mt19937 generator(options.seed + 2);
    std::uniform_int_distribution<int> distribution(0, 255);
    for (int y = 0; y < options.height; ++y) {
        const bool smooth = ((y / band_size) % 2) == 0;
        for (int x = 0; x < options.width; ++x) {
            const unsigned char value = smooth ? 255 : static_cast<unsigned char>(distribution(generator));
            set_pixel(image, options.width, x, y, value);
        }
    }
    return write_image(options.output / ("control_bands_256_" + dimensions(options)), image, options);
}

bool parse_positive_int(const char* text, int& value) {
    try {
        const int parsed = std::stoi(text);
        if (parsed <= 0) return false;
        value = parsed;
        return true;
    } catch (...) {
        return false;
    }
}

bool parse_options(int argc, char** argv, Options& options) {
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if ((argument == "--output" || argument == "--width" || argument == "--height" || argument == "--seed") && index + 1 >= argc) {
            return false;
        }
        if (argument == "--output") options.output = argv[++index];
        else if (argument == "--width") {
            if (!parse_positive_int(argv[++index], options.width)) return false;
        } else if (argument == "--height") {
            if (!parse_positive_int(argv[++index], options.height)) return false;
        }
        else if (argument == "--seed") {
            int seed = 0;
            if (!parse_positive_int(argv[++index], seed)) return false;
            options.seed = static_cast<unsigned int>(seed);
        } else {
            return false;
        }
    }
    return true;
}

int main(int argc, char** argv) {
    Options options;
    if (!parse_options(argc, argv, options)) {
        std::cerr << "Uso: " << argv[0] << " [--output DIRETORIO] [--width N] [--height N] [--seed N]\n";
        return 2;
    }

    std::error_code error;
    fs::create_directories(options.output, error);
    if (error) {
        std::cerr << "Erro ao criar " << options.output << ": " << error.message() << "\n";
        return 1;
    }

    std::cout << "Gerando controles determinísticos em " << options.width << "x" << options.height << "\n";
    return generate_smooth(options) && generate_noise(options) && generate_half_noise(options) && generate_bands(options) ? 0 : 1;
}
