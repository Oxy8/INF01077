#include <gtk/gtk.h>

struct TwoSpins {
    GtkWidget* spin_a;
    GtkWidget* spin_b;
};


// Estrutura pra passar tudo que o callback precisa
typedef struct {
    GtkWidget* kernel_entries[3][3];
    GtkWidget* clamp_direct;
    GtkWidget* clamp_offset;
    GtkWidget* single_channel;
    GtkWidget* three_channels;
} ConvolutionWidgets;

// Estrutura para armazenar estado da imagem atual
struct ImageState {
    unsigned char* data;
    int width, height;
    GtkWidget* picture;
    GtkWidget* window;
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
void update_picture(ImageState& img);
void compute_histogram(ImageState& img,  unsigned int hist[256], bool convert_to_gray_scale);
void adjust_contrast(ImageState& img, float contrast_factor);
void apply_negative(ImageState& img);
void compute_normalized_cummulative_histogram(ImageState& img, unsigned int hist[256]);
void equalize_histogram(ImageState& img, unsigned int cummulative_hist[256]);
unsigned char find_shade_level_closest_to(int value, unsigned int target_hist[256]);
void histogram_matching(ImageState& src_img, ImageState& target_img);
void zoom_in_image(ImageState& img);
void zoom_out_image(ImageState& img, Rectangle& rec);
void compute_rgb_avg_on_rectangle(unsigned char avg[3], int rec_x, int rec_y, int rec_width, int red_height, ImageState& img);
void rotate_90_degrees_clockwise(ImageState& img);
void rotate_90_degrees_counterclockwise(ImageState& img);
void apply_3_by_3_convolution(ImageState& img, float kernel[3][3], bool clamp_offset, bool single_channel);
inline unsigned char clamp_value(float value);









