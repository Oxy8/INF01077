#include <array>
#include <vector>

// Estrutura para armazenar estado da imagem atual
struct ImageState {
    unsigned char* data;
    int width, height;
    bool isGrayScale;

};

struct Rectangle {
    int x, y;
    int width, height;
};

void reset(ImageState& img, unsigned char* original_data, int original_width, int original_height);
bool load_image(const char* filename, ImageState& img);
void save_image(ImageState& img, const char* filename);
void apply_gray_scale_inplace(ImageState& img);
void flip_horizontal(ImageState& img);
void adjust_brightness(ImageState& img, int adjust_value);
void flip_vertical(ImageState& img);
std::array<unsigned char, 2> find_min_and_max_luminance_on_gray_scale_image(int width, int height, unsigned char* data);
void quantize_gray(ImageState& img, int levels);
void compute_histogram(ImageState& img,  unsigned int hist[256], bool convert_to_gray_scale);
void adjust_contrast(ImageState& img, float contrast_factor);
void apply_negative(ImageState& img);
void compute_normalized_cummulative_histogram(ImageState& img, unsigned int hist[256]);
void equalize_histogram(ImageState& img, unsigned int cummulative_hist[256]);
unsigned char find_shade_level_closest_to(int value, unsigned int target_hist[256]);
void histogram_matching(ImageState& src_img, ImageState& target_img);
void zoom_in_image(ImageState& img);
// Executa somente o kernel de zoom, com entrada e saída já alocadas. É usado
// pela coleta VTune para repetir o mesmo trabalho sem criações de imagem ou
// cópias de restauração entre as iterações.
bool zoom_in_image_to_buffer(const ImageState& source, unsigned char* destination, int destination_width, int destination_height);
void zoom_out_image(ImageState& img, Rectangle& rec);
void compute_rgb_avg_on_rectangle(unsigned char avg[3], int rec_x, int rec_y, int rec_width, int red_height, ImageState& img);
void rotate_90_degrees_clockwise(ImageState& img);
void rotate_90_degrees_counterclockwise(ImageState& img);
bool apply_3_by_3_convolution(ImageState& img, const float kernel[3][3], bool clamp_offset, bool single_channel);
bool apply_5_by_5_convolution(ImageState& img, const float kernel[5][5], bool clamp_offset, bool single_channel);
bool apply_7_by_7_convolution(ImageState& img, const float kernel[7][7], bool clamp_offset, bool single_channel);
bool apply_9_by_9_convolution(ImageState& img, const float kernel[9][9], bool clamp_offset, bool single_channel);
bool apply_11_by_11_convolution(ImageState& img, const float kernel[11][11], bool clamp_offset, bool single_channel);
bool compute_sobel_detail_map(const ImageState& image, std::vector<unsigned char>& detail_map);
bool apply_varying_window_gaussian_denoising(ImageState& image);

extern const float GAUSSIAN_KERNEL_3X3[3][3];
extern const float GAUSSIAN_KERNEL_5X5[5][5];
extern const float GAUSSIAN_KERNEL_7X7[7][7];
extern const float GAUSSIAN_KERNEL_9X9[9][9];
extern const float GAUSSIAN_KERNEL_11X11[11][11];
inline unsigned char clamp_value(float value);









