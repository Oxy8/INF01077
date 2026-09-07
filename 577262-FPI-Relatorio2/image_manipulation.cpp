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

#include "image_manipulation.h"

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

// These helpers process exactly one destination pixel. They are force-inlined
// because the wrappers call them once for every valid pixel in the image.
static CONVOLUTION_ALWAYS_INLINE void apply_3_by_3_convolution_to_pixel(
    const ImageState& img,
    int x,
    int y,
    const float kernel[3][3],
    bool clamp_offset,
    bool single_channel,
    unsigned char* destination
) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -1; k <= 1; ++k) {
            for (int l = -1; l <= 1; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[1 + k][1 + l] * img.data[source_index];
            }
        }

        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = value;
        destination[1] = value;
        destination[2] = value;
        return;
    }

    float sum_r = 0.0f;
    float sum_g = 0.0f;
    float sum_b = 0.0f;
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
    const ImageState& img,
    int x,
    int y,
    const float kernel[5][5],
    bool clamp_offset,
    bool single_channel,
    unsigned char* destination
) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -2; k <= 2; ++k) {
            for (int l = -2; l <= 2; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[2 + k][2 + l] * img.data[source_index];
            }
        }

        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = value;
        destination[1] = value;
        destination[2] = value;
        return;
    }

    float sum_r = 0.0f;
    float sum_g = 0.0f;
    float sum_b = 0.0f;
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
    const ImageState& img,
    int x,
    int y,
    const float kernel[7][7],
    bool clamp_offset,
    bool single_channel,
    unsigned char* destination
) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -3; k <= 3; ++k) {
            for (int l = -3; l <= 3; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[3 + k][3 + l] * img.data[source_index];
            }
        }

        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = value;
        destination[1] = value;
        destination[2] = value;
        return;
    }

    float sum_r = 0.0f;
    float sum_g = 0.0f;
    float sum_b = 0.0f;
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
    const ImageState& img,
    int x,
    int y,
    const float kernel[9][9],
    bool clamp_offset,
    bool single_channel,
    unsigned char* destination
) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -4; k <= 4; ++k) {
            for (int l = -4; l <= 4; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[4 + k][4 + l] * img.data[source_index];
            }
        }

        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = value;
        destination[1] = value;
        destination[2] = value;
        return;
    }

    float sum_r = 0.0f;
    float sum_g = 0.0f;
    float sum_b = 0.0f;
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
    const ImageState& img,
    int x,
    int y,
    const float kernel[11][11],
    bool clamp_offset,
    bool single_channel,
    unsigned char* destination
) {
    if (single_channel) {
        float sum = 0.0f;
        for (int k = -5; k <= 5; ++k) {
            for (int l = -5; l <= 5; ++l) {
                const int source_index = ((y - k) * img.width + (x - l)) * 3;
                sum += kernel[5 + k][5 + l] * img.data[source_index];
            }
        }

        const unsigned char value = clamp_value(sum + (clamp_offset ? 127.0f : 0.0f));
        destination[0] = value;
        destination[1] = value;
        destination[2] = value;
        return;
    }

    float sum_r = 0.0f;
    float sum_g = 0.0f;
    float sum_b = 0.0f;
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

#undef CONVOLUTION_ALWAYS_INLINE

bool apply_3_by_3_convolution(ImageState& img, const float kernel[3][3], bool clamp_offset, bool single_channel) {
    if (img.width < 3 || img.height < 3) {
        fprintf(stderr, "Imagem muito pequena para realizar operação de convolução 3x3!\n");
        return false;
    }

    // Ignora uma linha/coluna em cada borda para manter apenas pixels cuja
    // vizinhança 3x3 está completamente dentro da imagem.
    const int new_width = img.width - 2;
    const int new_height = img.height - 2;
    unsigned char* new_img_data = (unsigned char*) malloc(
        static_cast<size_t>(new_width) * new_height * 3
    );
    if (!new_img_data) {
        fprintf(stderr, "Falha ao alocar memória para convolução 3x3!\n");
        return false;
    }

    for (int j = 1; j < img.height - 1; ++j) {
        for (int i = 1; i < img.width - 1; ++i) {
            unsigned char* destination = new_img_data
                + ((j - 1) * new_width + (i - 1)) * 3;
            apply_3_by_3_convolution_to_pixel(
                img, i, j, kernel, clamp_offset, single_channel, destination
            );
        }
    }

    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_5_by_5_convolution(ImageState& img, const float kernel[5][5], bool clamp_offset, bool single_channel) {
    if (img.width < 5 || img.height < 5) {
        fprintf(stderr, "Imagem muito pequena para realizar operação de convolução 5x5!\n");
        return false;
    }

    const int new_width = img.width - 4;
    const int new_height = img.height - 4;
    unsigned char* new_img_data = (unsigned char*) malloc(
        static_cast<size_t>(new_width) * new_height * 3
    );
    if (!new_img_data) {
        fprintf(stderr, "Falha ao alocar memória para convolução 5x5!\n");
        return false;
    }

    for (int j = 2; j < img.height - 2; ++j) {
        for (int i = 2; i < img.width - 2; ++i) {
            unsigned char* destination = new_img_data
                + ((j - 2) * new_width + (i - 2)) * 3;
            apply_5_by_5_convolution_to_pixel(
                img, i, j, kernel, clamp_offset, single_channel, destination
            );
        }
    }

    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_7_by_7_convolution(ImageState& img, const float kernel[7][7], bool clamp_offset, bool single_channel) {
    if (img.width < 7 || img.height < 7) {
        fprintf(stderr, "Imagem muito pequena para realizar operação de convolução 7x7!\n");
        return false;
    }

    const int new_width = img.width - 6;
    const int new_height = img.height - 6;
    unsigned char* new_img_data = (unsigned char*) malloc(
        static_cast<size_t>(new_width) * new_height * 3
    );
    if (!new_img_data) {
        fprintf(stderr, "Falha ao alocar memória para convolução 7x7!\n");
        return false;
    }

    for (int j = 3; j < img.height - 3; ++j) {
        for (int i = 3; i < img.width - 3; ++i) {
            unsigned char* destination = new_img_data
                + ((j - 3) * new_width + (i - 3)) * 3;
            apply_7_by_7_convolution_to_pixel(
                img, i, j, kernel, clamp_offset, single_channel, destination
            );
        }
    }

    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_9_by_9_convolution(ImageState& img, const float kernel[9][9], bool clamp_offset, bool single_channel) {
    if (img.width < 9 || img.height < 9) {
        fprintf(stderr, "Imagem muito pequena para realizar operação de convolução 9x9!\n");
        return false;
    }

    const int new_width = img.width - 8;
    const int new_height = img.height - 8;
    unsigned char* new_img_data = (unsigned char*) malloc(
        static_cast<size_t>(new_width) * new_height * 3
    );
    if (!new_img_data) {
        fprintf(stderr, "Falha ao alocar memória para convolução 9x9!\n");
        return false;
    }

    for (int j = 4; j < img.height - 4; ++j) {
        for (int i = 4; i < img.width - 4; ++i) {
            unsigned char* destination = new_img_data
                + ((j - 4) * new_width + (i - 4)) * 3;
            apply_9_by_9_convolution_to_pixel(
                img, i, j, kernel, clamp_offset, single_channel, destination
            );
        }
    }

    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}

bool apply_11_by_11_convolution(ImageState& img, const float kernel[11][11], bool clamp_offset, bool single_channel) {
    if (img.width < 11 || img.height < 11) {
        fprintf(stderr, "Imagem muito pequena para realizar operação de convolução 11x11!\n");
        return false;
    }

    const int new_width = img.width - 10;
    const int new_height = img.height - 10;
    unsigned char* new_img_data = (unsigned char*) malloc(
        static_cast<size_t>(new_width) * new_height * 3
    );
    if (!new_img_data) {
        fprintf(stderr, "Falha ao alocar memória para convolução 11x11!\n");
        return false;
    }

    for (int j = 5; j < img.height - 5; ++j) {
        for (int i = 5; i < img.width - 5; ++i) {
            unsigned char* destination = new_img_data
                + ((j - 5) * new_width + (i - 5)) * 3;
            apply_11_by_11_convolution_to_pixel(
                img, i, j, kernel, clamp_offset, single_channel, destination
            );
        }
    }

    free(img.data);
    img.data = new_img_data;
    img.height = new_height;
    img.width = new_width;
    return true;
}



void rotate_90_degrees_clockwise(ImageState& img){
    int new_img_height = img.width;
    int new_img_width = img.height;

    unsigned char* new_data = (unsigned char*) malloc(new_img_height * new_img_width * 3);

    // Copia os valores, transformando colunas da imagem original em linhas da nova imagem
    // Como é no sentido horário, começa da primeira coluna e última linha
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

    // Copia os valores, transformando colunas da imagem original em linhas da nova imagem
    // Como é no sentido anti-horário, começa da última coluna e primeira linha
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

    if(h > INT_MAX){
        printf("ERRO: imagem muito grande para dar mais zoom in!\n");
        return;
    }

    long long w  = 1LL * img.width * 2 - 1;

    if(w > INT_MAX){
        printf("ERRO: imagem muito grande para dar mais zoom in!\n");
        return;
    }

    long long total = h * w * 3LL;

    if (total > INT_MAX) {
        printf("ERRO: imagem muito grande para dar mais zoom in!\n");
        return;
    }

    int new_height = (int) h;
    int new_width = (int) w;

    unsigned char* new_data = (unsigned char*) malloc(new_width * new_height * 3);

    // Copia os valores
    for(int j = 0; j < img.height; j++){
        for(int i = 0; i < img.width; i++){
            int old_index = (j * img.width + i) * 3;
            int new_index = (j * 2 * new_width + i * 2) * 3;

            memcpy(new_data + new_index, img.data + old_index, 3);
        }

    }

    // Interpola as linhas
    for(int j = 0; j < new_height; j += 2){
        for(int i = 1; i < new_width; i += 2){
            int index = (j * new_width + i) * 3;


            new_data[index] = (unsigned char) ((new_data[index - 3] + new_data[index + 3]) / 2);
            new_data[index + 1] = (unsigned char) ((new_data[index - 3 + 1] + new_data[index + 3 + 1]) / 2);
            new_data[index + 2] = (unsigned char) ((new_data[index - 3 + 2] + new_data[index + 3 + 2]) / 2);

        }

    }

    // Interpola as colunas
    for(int j = 1; j < new_height; j += 2){
        for(int i = 0; i < new_width; i++){
            int index = (j * new_width + i) * 3;

            unsigned char interpolated_red, interpolated_green, interpolated_blue;

            interpolated_red = (unsigned char) ((new_data[index - new_width * 3] + new_data[index + new_width * 3]) / 2);
            interpolated_green = (unsigned char) ((new_data[index - new_width * 3 + 1] + new_data[index + new_width * 3 + 1]) / 2);
            interpolated_blue = (unsigned char) ((new_data[index - new_width * 3 + 2] + new_data[index + new_width * 3 + 2]) / 2);

            new_data[index] = interpolated_red;
            new_data[index + 1] = interpolated_green;
            new_data[index + 2] = interpolated_blue;
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

    unsigned char avg_red, avg_green, avg_blue;
    unsigned char avg[3];

    for(int j = 0; j < new_height; j++){
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
    unsigned long long sum_r = 0;
    unsigned long long sum_g = 0;
    unsigned long long sum_b = 0;
    int num_pixels = 0;

    for(int j = rec_y; j < rec_y + rec_height; j++){

        if(j >= img.height)
            break;
        
            
        
        for(int i = rec_x; i < rec_x + rec_width; i++){

            if(i >= img.width)
                break;


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


    for(int i = 0; i < 256; i++)
        src_hist[i] = find_shade_level_closest_to(src_hist[i], target_hist);

    for(int i = 0; i < src_img.height; i++){
        for(int j = 0; j < src_img.width; j++){
            int index = (i * src_img.width + j) * 3;
            for(int channel = 0; channel < 3; channel++){
                unsigned char old_value = src_img.data[index + channel];
                unsigned char new_value = src_hist[old_value];
                src_img.data[index + channel] = new_value; 
            }
        }
    }

}

unsigned char find_shade_level_closest_to(int value, unsigned int target_hist[256]) {
    auto pointer_to_closest_value = std::lower_bound(target_hist, target_hist + 256, value); // std::lower_bound busca no intervalo [first, last)

    if(pointer_to_closest_value == target_hist)
        return 0;

    int idx = pointer_to_closest_value - target_hist;

    // std::lower_bound retorna o primeiro elemento que é >= value
    // Então precisamos ver se esse elemento é realmente o mais próximo ou se o anterior é mais próximo. Já garantimos que idx > 0
    if (std::abs((int)target_hist[idx] - value) < std::abs((int)target_hist[idx - 1] - value))
        return (unsigned char) idx;
    else
        return (unsigned char) (idx - 1);
}


void equalize_histogram(ImageState& img, unsigned int cummulative_hist[256]){

    compute_normalized_cummulative_histogram(img, cummulative_hist);
    
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

    // Primeiro calculo o histograma acumulado e só após faço a normalização pelo fator, para evitar encadeamento de erros de arredondamento
    for(int i = 1; i < 256; i++){
        hist[i] = hist[i - 1] + hist[i];
    }

    for(int i = 0; i < 256; i++){
        hist[i] = std::round(hist[i] * normalize_factor);
    }



}


void apply_negative(ImageState& img){

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
    if(contrast_factor == 1.0f)
        return;

    unsigned char min = 255;

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
            for (int j = 0; j < img.height; j++) {
                for (int i = 0; i < img.width; i++) {
                    int index = (j * img.width + i) * 3;
                    unsigned char r = img.data[index];
                    unsigned char g = img.data[index + 1];
                    unsigned char b = img.data[index + 2];
                    unsigned char gray = (unsigned char)(0.299 * r + 0.587 * g + 0.114 * b);
            
                    hist[gray] += 1; // Conta 3 vezes, uma para cada canal
                }
            }
            
            return;
        }
    }
        
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

// Carrega uma imagem para ImageState, garantindo buffer próprio
bool load_image(const char* filename, ImageState& img) {
    int width, height, channels;

    // Força 3 canais (RGB)
    unsigned char* pixels = stbi_load(filename, &width, &height, &channels, 3);
    if (!pixels) {
        return false;
    }

    img.width = width;
    img.height = height;
    img.isGrayScale = false;

    // Cria buffer próprio
    img.data = (unsigned char*) malloc(width * height * 3);
    if (!img.data) {
        stbi_image_free(pixels);
        return false;
    }

    memcpy(img.data, pixels, width * height * 3);

    stbi_image_free(pixels); // libera buffer do stb

    return true;
}


void apply_gray_scale_inplace(ImageState& img) {

    if(img.isGrayScale)
        return;

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
    if(adjust_value == 0)
        return;

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

    unsigned char *pixel_buffer = (unsigned char*) malloc(3);

    // Vai trocando os pixels de cada linha para invertê-las
    for (int j = 0; j < height; j++) {
        for (int i = 0; i < width / 2; i++) {
            memcpy(pixel_buffer, img.data + (j * width + i) * 3, 3);
            memcpy(img.data + (j * width + i) * 3,
                   img.data + (j * width + (width - 1 - i)) * 3, 3);
            memcpy(img.data + (j * width + (width - 1 - i)) * 3, pixel_buffer, 3);
        }
    }

    free(pixel_buffer);
}


void flip_vertical(ImageState& img){
    int width = img.width;
    int height = img.height;
    unsigned char *row_buffer = (unsigned char*) malloc(width * 3);

    // Vai trocando as linhas para inverter a imagem
    for(int j = 0; j < height / 2; j++){
        memcpy(row_buffer, img.data + j * width * 3, width * 3);
        memcpy(img.data + j * width * 3, img.data + (height - 1 - j) * width * 3, width * 3);
        memcpy(img.data + (height - 1 - j) * width * 3, row_buffer, width * 3);
    }

    free(row_buffer);
} 


std::array<unsigned char, 2> find_min_and_max_luminance_on_gray_scale_image(int width, int height, unsigned char* data){
    unsigned char min_luminance = 255;
    unsigned char max_luminance = 0;

    for(int j = 0; j < height; j++){
        for(int i = 0; i < width; i++){
            int index = (j * width + i) * 3; // Pro caso de 3 canis de cores, mas estamos forçando a leitura em 3 canais de cores
            unsigned char luminance = data[index]; // R = G = B = gray

            if(luminance < min_luminance)
                min_luminance = luminance;
            
            if(luminance > max_luminance)
                max_luminance = luminance;
        }
    }

    return {min_luminance, max_luminance};
}
    

void quantize_gray(ImageState& img, int levels) {
    // Garante que a imagem está em escala de cinza aplicando ela. Não é o ideal, mas simplifica o código.
    // Se a imagem já estiver em escala de cinza, não tem problema aplicar de novo.

    if(!img.isGrayScale)
        apply_gray_scale_inplace(img);

    std::array<unsigned char, 2> min_and_max_l = find_min_and_max_luminance_on_gray_scale_image(img.width, img.height, img.data);

    unsigned char min_l = min_and_max_l[0];
    unsigned char max_l = min_and_max_l[1];

    int num_levels = max_l - min_l + 1;

    if (num_levels <= levels) 
        // Não faz sentido quantizar
        return;

    float tb = (float) num_levels / levels;

    for (int j = 0; j < img.height; j++) {
        for (int i = 0; i < img.width; i++) {
                int index = (j * img.width + i) * 3; // O buffer permanece com três canais RGB.
                unsigned char luminance = img.data[index]; 

                // Encontrando o intervalo em que o valor de luminância se encontra
                // Bin k = [ t1 ​− 0.5 + k * tb, t1 ​− 0.5 + (k + 1) * tb), como luminance está no interior do bin k então
                // t1 ​− 0.5 + k * tb <= luminance ​< t1 ​− 0.5 + (k + 1) * tb
                    // Isolando k dessa expressão temos:
                    // k <= (luminance ​− (t1 ​− 0.5)) / tb ​< k + 1
                int new_luminance_bin = (int) ((luminance - min_l + 0.5) / tb); 

                // O novo valor de luminância será o centro do bin:
                // centro_bin = t1 - 0.5 + (k * tb) + (tb / 2) -> O valor mínimo de todos os intervalos + deslocamento de k bins + deslocamento até o meio do bin
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
    else
        printf("ERRO CRÍTICO: sem imagem original para resetar!\n");
}
