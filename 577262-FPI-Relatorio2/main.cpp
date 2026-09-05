

#include <cairo.h>
#include <gtk/gtk.h>
#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <array>
#include <algorithm>

#include "image_manipulation.h"


void on_activate(GtkApplication* app, gpointer user_data);
void close_application(GtkApplication* app);
void on_image_window_close(GtkWidget* widget, gpointer app_ptr);
void on_tools_window_close(GtkWidget* widget, gpointer app_ptr);



std::vector<ImageState> images;  // máximo 2 cópias -> 3 elementos
int num_images_saved = 0;
unsigned char* original_data = nullptr;
int original_width, original_height;

unsigned int histogram[256];




static void draw_histogram(GtkDrawingArea *area, cairo_t *cr, int width, int height, gpointer user_data) {
    unsigned int* hist = (unsigned int*) user_data;
    int max_val = 0;
    int max_index = 0;
    for (int i = 0; i < 256; i++) {
        if (hist[i] > max_val) {
            max_val = hist[i];
            max_index = i;
        }
    }

    int padding_left = 40;   // espaço p/ eixo Y e rótulos
    int padding_right = 20;  // margem direita
    int padding_bottom = 30; // espaço p/ eixo X e rótulos
    int padding_top = 20;    // margem superior

    float plot_width  = width - padding_left - padding_right;
    float plot_height = height - padding_top - padding_bottom;

    float scale_y = (float)plot_height / max_val;
    float scale_x = plot_width / 256.0f;

    // fundo branco
    cairo_set_source_rgb(cr, 1, 1, 1);
    cairo_paint(cr);

    // cor preta
    cairo_set_source_rgb(cr, 0, 0, 0);

    // --- Eixo X ---
    cairo_move_to(cr, padding_left, height - padding_bottom);
    cairo_line_to(cr, width - padding_right, height - padding_bottom);
    cairo_stroke(cr);

    // --- Eixo Y ---
    cairo_move_to(cr, padding_left, height - padding_bottom);
    cairo_line_to(cr, padding_left, padding_top);
    cairo_stroke(cr);

    // --- Rótulos eixo X (0, 64, 128, 192, 255) ---
    int ticks_x[] = {0, 64, 128, 192, 255};
    for (int t = 0; t < 5; t++) {
        int val = ticks_x[t];
        float x = padding_left + val * scale_x;

        // linha pequena de tick
        cairo_move_to(cr, x, height - padding_bottom);
        cairo_line_to(cr, x, height - padding_bottom + 5);
        cairo_stroke(cr);

        // texto
        char buf[16];
        snprintf(buf, sizeof(buf), "%d", val);
        cairo_move_to(cr, x - 10, height - 10);
        cairo_show_text(cr, buf);
    }

    // Rótulos eixo Y (25%, 50%, 75%, 100%)
    int ticks_y[] = {max_val / 4, max_val / 2, (3 * max_val) / 4, max_val};
    for (int t = 0; t < 4; t++) {
        int val = ticks_y[t];
        float y = height - padding_bottom - val * scale_y;

        // linha pequena de tick
        cairo_move_to(cr, padding_left - 5, y);
        cairo_line_to(cr, padding_left, y);
        cairo_stroke(cr);

        // texto
        char buf[32];
        snprintf(buf, sizeof(buf), "%d", val);
        cairo_move_to(cr, 5, y + 5);
        cairo_show_text(cr, buf);
    }

    // Barras do histograma
    cairo_set_source_rgb(cr, 0, 0, 0);
    for (int i = 0; i < 256; i++) {
        float x = padding_left + i * scale_x;
        float h = hist[i] * scale_y;
        cairo_rectangle(cr, x, height - padding_bottom - h, scale_x, h);
    }
    cairo_fill(cr);

    // Destaca barra mais alta
    float peak_x = padding_left + max_index * scale_x + scale_x / 2;
    float peak_y = height - padding_bottom - max_val * scale_y;

    cairo_set_source_rgb(cr, 1, 0, 0); // vermelho
    cairo_arc(cr, peak_x, peak_y, 3, 0, 2 * M_PI);
    cairo_fill(cr);
}


//--------------------------------
// Callbacks dos botões GTK
//--------------------------------

void on_copy(GtkButton*, gpointer app_ptr) {
    
    if (images.size() >= 3) {
        printf("Limite de 2 cópias da imagem atingido!\n");
        return;
    }

    ImageState base = images.back();
    unsigned char* new_data = (unsigned char*) malloc(base.width * base.height * 3);
    memcpy(new_data, base.data, base.width * base.height * 3);

    GtkWidget* win = gtk_window_new();
    GtkWidget* pic = gtk_picture_new();

    g_signal_connect(win, "destroy", G_CALLBACK(on_image_window_close), app_ptr);

    gtk_window_set_child(GTK_WINDOW(win), pic);
    gtk_widget_show(win);

    ImageState copy{new_data, base.width, base.height, pic, win};
    images.push_back(copy);

    update_picture(images.back());
}

void on_gray(GtkButton*, gpointer) {
    apply_gray_scale_inplace(images.back());
}

void on_flip_h(GtkButton*, gpointer) {
    flip_horizontal(images.back());
}

void on_flip_v(GtkButton*, gpointer) {
    flip_vertical(images.back());
}

void on_reset(GtkButton*, gpointer) {
    reset(images.back(), original_data, original_width, original_height);
}

void on_adjust_brightness(GtkButton*, gpointer spin_brightness){
    int brightness_value = gtk_spin_button_get_value_as_int(GTK_SPIN_BUTTON(spin_brightness));
    adjust_brightness(images.back(), brightness_value);
}


float parse_float(const char* text) {
    if (!text) 
        throw std::invalid_argument("Entrada nula");

    std::string s(text);

    // Troca ponto por vírgula para aceitar ambos os formatos
    std::replace(s.begin(), s.end(), '.', ',');

    try {
        return std::stof(s);
    } catch (const std::exception&) {
        throw std::invalid_argument("Valor inválido");
    }
}

void on_adjust_contrast(GtkButton*, gpointer entry_contrast){
    const char* text = gtk_editable_get_text(GTK_EDITABLE(entry_contrast));

    if(text == NULL || *text == '\0'){
        printf("Insira um valor de contraste para executar a operação!");
        return;
    }

    float contrast_value = parse_float(text);

    adjust_contrast(images.back(), contrast_value);
}


void on_equalize_histogram(GtkButton*, gpointer) {
    unsigned int cummulative_hist[256];
    equalize_histogram(images.back(), cummulative_hist);
}


void on_save(GtkButton*, gpointer) {

    std::string file_name = "saida" + (num_images_saved > 0 ? std::to_string(num_images_saved) : "") + ".jpg";
    const char* c_file_name = file_name.c_str();

    save_image(images.back(), c_file_name);
    num_images_saved++;
}

void on_quantize(GtkButton*, gpointer spin) {
    int levels = gtk_spin_button_get_value_as_int(GTK_SPIN_BUTTON(spin));
    quantize_gray(images.back(), levels);
}

void on_apply_negative(GtkButton*, gpointer) {
    apply_negative(images.back());
}

void on_zoom_in(GtkButton*, gpointer) {
    zoom_in_image(images.back());
}

void on_zoom_out(GtkButton*, gpointer spins) {

    TwoSpins* s = (TwoSpins*) spins;

    int sx = gtk_spin_button_get_value(GTK_SPIN_BUTTON(s->spin_a));
    int sy = gtk_spin_button_get_value(GTK_SPIN_BUTTON(s->spin_b));

    Rectangle rec{0, 0, sx, sy};

    if(sx <= 0 || sy <= 0) {
        printf("Fatores de escala devem ser maiores que 0!\n");
        return;
    }

    zoom_out_image(images.back(), rec);
}

void on_rotate_90_clockise(GtkButton*, gpointer) {
    rotate_90_degrees_clockwise(images.back());
}

void on_rotate_90_counterclockise(GtkButton*, gpointer) {
    rotate_90_degrees_counterclockwise(images.back());
}

void on_hist_matching(GtkButton*, gpointer) {
    ImageState target_image;
    ImageState& src_image = images.back();

    std::string name;
    printf("Digite o nome do arquivo da imagem alvo (string vazia para cancelar): ");
    std::getline(std::cin, name);  // lê até o enter

    const char* c_file_name = name.c_str();

    if(c_file_name[0] == '\0')
        return;

    while (!load_image(c_file_name, target_image)) {
        printf("Erro ao carregar a imagem alvo!\n---------------------\n");

        printf("Digite o nome do arquivo da imagem alvo (string vazia para cancelar): ");
        std::getline(std::cin, name);  // lê até o enter
        c_file_name = name.c_str();

        if(c_file_name[0] == '\0')
            return;
    }

    histogram_matching(src_image, target_image);
}

// Handler do botão de calcular histograma
static void on_histogram_button_clicked(GtkWidget *button, gpointer user_data) {
    ImageState& curr_image = images.back();

    compute_histogram(curr_image, histogram, true);

    // Criar nova janela
    GtkWidget *window = gtk_window_new();
    gtk_window_set_title(GTK_WINDOW(window), "Histograma");
    gtk_window_set_default_size(GTK_WINDOW(window), 500, 300);

    // Criar área de desenho
    GtkWidget *drawing_area = gtk_drawing_area_new();
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(drawing_area),
                                   draw_histogram,
                                   histogram, NULL);

    gtk_window_set_child(GTK_WINDOW(window), drawing_area);

    gtk_widget_show(window); // exibe a janela do histograma
}


void on_load_new_image(GtkButton*, gpointer app_ptr) {
    // Carrega uma nova imagem em uma nova janela, ainda respeitando o limite de no máximo 3 janelas de imagens
    if (images.size() >= 3) {
        printf("Limite de 3 janelas de imagem atingido!\n");
        return;
    }

    ImageState base = images.back();

    std::string name;
    printf("Digite o nome do arquivo (string vazia para cancelar): ");
    std::getline(std::cin, name);  // lê até o enter

    const char* c_file_name = name.c_str();

    while (c_file_name[0] != '\0' && !load_image(c_file_name, base)) {
        printf("Erro ao carregar a imagem!\n---------------------\n");

        printf("Digite o nome do arquivo (string vazia para cancelar): ");
        std::getline(std::cin, name);  // lê até o enter
        c_file_name = name.c_str();
    }

    if(c_file_name[0] == '\0')
        return;


    unsigned char* new_data = (unsigned char*) malloc(base.width * base.height * 3);
    memcpy(new_data, base.data, base.width * base.height * 3);

    GtkWidget* win = gtk_window_new();
    GtkWidget* pic = gtk_picture_new();

    g_signal_connect(win, "destroy", G_CALLBACK(on_image_window_close), app_ptr);

    gtk_window_set_child(GTK_WINDOW(win), pic);
    gtk_widget_show(win);

    ImageState copy{new_data, base.width, base.height, pic, win};
    images.push_back(copy);

    update_picture(images.back());
    
}



// Função genérica para preencher o grid com valores de kernel
void set_kernel_entries(ConvolutionWidgets* cw, float kernel[3][3]) {
    char buffer[32];
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            snprintf(buffer, sizeof(buffer), "%g", kernel[i][j]);
            gtk_entry_buffer_set_text(gtk_entry_get_buffer(GTK_ENTRY(cw->kernel_entries[i][j])), buffer, -1);
        }
    }
}

void on_kernel_button_clicked(GtkButton* button, gpointer user_data) {
    ConvolutionWidgets* cw = (ConvolutionWidgets*) user_data;
    const char* label = gtk_button_get_label(button);

    float kernel[3][3];

    
    if (strcmp(label, "Gaussiano") == 0) {
        float g[3][3] = { {0.0625,0.125,0.0625}, {0.125,0.25,0.125}, {0.0625,0.125,0.0625} };
        memcpy(kernel, g, sizeof(g));
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->clamp_direct), TRUE);
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->three_channels), TRUE);

    } else if (strcmp(label, "Laplaciano") == 0) {
        float l[3][3] = { {0,-1,0}, {-1,4,-1}, {0,-1,0} };
        memcpy(kernel, l, sizeof(l));
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->clamp_direct), TRUE);
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->single_channel), TRUE);


    } else if (strcmp(label, "Passa Altas Genérico") == 0) {
        float p[3][3] = { {-1,-1,-1}, {-1,8,-1}, {-1,-1,-1} };
        memcpy(kernel, p, sizeof(p));
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->clamp_direct), TRUE);
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->single_channel), TRUE);

    } else if (strcmp(label, "Prewitt Hx") == 0) {
        float k[3][3] = { {-1,0,1}, {-1,0,1}, {-1,0,1} };
        memcpy(kernel, k, sizeof(k));
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->clamp_offset), TRUE);
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->single_channel), TRUE);

    } else if (strcmp(label, "Prewitt Hy") == 0) {
        float k[3][3] = { {-1,-1,-1}, {0,0,0}, {1,1,1} };
        memcpy(kernel, k, sizeof(k));
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->clamp_offset), TRUE);
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->single_channel), TRUE);

    } else if (strcmp(label, "Sobel Hx") == 0) {
        float k[3][3] = { {-1,0,1}, {-2,0,2}, {-1,0,1} };
        memcpy(kernel, k, sizeof(k));
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->clamp_offset), TRUE);
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->single_channel), TRUE);

    } else if (strcmp(label, "Sobel Hy") == 0) {
        float k[3][3] = { {-1,-2,-1}, {0,0,0}, {1,2,1} };
        memcpy(kernel, k, sizeof(k));
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->clamp_offset), TRUE);
        gtk_check_button_set_active(GTK_CHECK_BUTTON(cw->single_channel), TRUE);

    } else return;

    set_kernel_entries(cw, kernel);
}


void on_apply_convolution(GtkButton* button, gpointer user_data) {
    ConvolutionWidgets* cw = (ConvolutionWidgets*) user_data;
    float kernel[3][3];

    // Lê os valores das entries
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            const char* text = gtk_entry_buffer_get_text(
                gtk_entry_get_buffer(GTK_ENTRY(cw->kernel_entries[i][j]))
            );
            kernel[i][j] = strtof(text, NULL);
        }
    }

    // Verifica a opção de clamping (ou + 127 ou clamp direto)
    bool clamp_offset = gtk_check_button_get_active(GTK_CHECK_BUTTON(cw->clamp_offset));
    // Verifica se é single_channel ou three_channels
    bool single_channel = gtk_check_button_get_active(GTK_CHECK_BUTTON(cw->single_channel));

    apply_3_by_3_convolution(images.back(), kernel, clamp_offset, single_channel);
}


void create_convolution_window(GtkApplication* app) {
    GtkWidget* window = gtk_application_window_new(app);
    gtk_window_set_title(GTK_WINDOW(window), "Convolução 3x3");
    gtk_window_set_default_size(GTK_WINDOW(window), 500, 400);

    GtkWidget* main_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 10);
    gtk_window_set_child(GTK_WINDOW(window), main_box);

    GtkWidget* grid = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(grid), 5);
    gtk_grid_set_column_spacing(GTK_GRID(grid), 5);
    gtk_box_append(GTK_BOX(main_box), grid);

    ConvolutionWidgets* cw = g_new0(ConvolutionWidgets, 1);


 

    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) {
            GtkWidget* entry = gtk_entry_new();
            gtk_entry_buffer_set_text(gtk_entry_get_buffer(GTK_ENTRY(entry)), "0", -1);
            gtk_grid_attach(GTK_GRID(grid), entry, j, i, 1, 1);
            cw->kernel_entries[i][j] = entry;
        }



    GtkWidget* channel_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(main_box), channel_box);

    GtkWidget* single_channel = gtk_check_button_new_with_label("Um canal de cor (escala de cinza)");
    GtkWidget* three_channels = gtk_check_button_new_with_label("3 canais de cores (RGB)");
    gtk_box_append(GTK_BOX(channel_box), single_channel);
    gtk_box_append(GTK_BOX(channel_box), three_channels);
    gtk_check_button_set_group(GTK_CHECK_BUTTON(single_channel), GTK_CHECK_BUTTON(three_channels));
    gtk_check_button_set_active(GTK_CHECK_BUTTON(single_channel), TRUE);

    cw->single_channel = single_channel;
    cw->three_channels = three_channels;


    GtkWidget* clamp_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(main_box), clamp_box);

    GtkWidget* clamp_direct = gtk_check_button_new_with_label("Clamp direto (0-255)");
    GtkWidget* clamp_offset = gtk_check_button_new_with_label("Clamp com +127");
    gtk_box_append(GTK_BOX(clamp_box), clamp_direct);
    gtk_box_append(GTK_BOX(clamp_box), clamp_offset);
    gtk_check_button_set_group(GTK_CHECK_BUTTON(clamp_offset), GTK_CHECK_BUTTON(clamp_direct));
    gtk_check_button_set_active(GTK_CHECK_BUTTON(clamp_direct), TRUE);

    cw->clamp_direct = clamp_direct;
    cw->clamp_offset = clamp_offset;

    GtkWidget* btn_box1 = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(main_box), btn_box1);

    GtkWidget* btn_kernel1 = gtk_button_new_with_label("Gaussiano");
    GtkWidget* btn_kernel2 = gtk_button_new_with_label("Laplaciano");
    GtkWidget* btn_kernel3 = gtk_button_new_with_label("Passa Altas Genérico");

    gtk_box_append(GTK_BOX(btn_box1), btn_kernel1);
    gtk_box_append(GTK_BOX(btn_box1), btn_kernel2);
    gtk_box_append(GTK_BOX(btn_box1), btn_kernel3);

    GtkWidget* btn_box2 = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(main_box), btn_box2);

    GtkWidget* btn_kernel4 = gtk_button_new_with_label("Prewitt Hx");
    GtkWidget* btn_kernel5 = gtk_button_new_with_label("Prewitt Hy");
    GtkWidget* btn_kernel6 = gtk_button_new_with_label("Sobel Hx");
    GtkWidget* btn_kernel7 = gtk_button_new_with_label("Sobel Hy");

    gtk_box_append(GTK_BOX(btn_box2), btn_kernel4);
    gtk_box_append(GTK_BOX(btn_box2), btn_kernel5);
    gtk_box_append(GTK_BOX(btn_box2), btn_kernel6);
    gtk_box_append(GTK_BOX(btn_box2), btn_kernel7);

    GtkWidget* btn_apply = gtk_button_new_with_label("Aplicar convolução");
    gtk_box_append(GTK_BOX(main_box), btn_apply);

    // Conectar sinais dos botões pré-definidos
    g_signal_connect(btn_kernel1, "clicked", G_CALLBACK(on_kernel_button_clicked), cw);
    g_signal_connect(btn_kernel2, "clicked", G_CALLBACK(on_kernel_button_clicked), cw);
    g_signal_connect(btn_kernel3, "clicked", G_CALLBACK(on_kernel_button_clicked), cw);
    g_signal_connect(btn_kernel4, "clicked", G_CALLBACK(on_kernel_button_clicked), cw);
    g_signal_connect(btn_kernel5, "clicked", G_CALLBACK(on_kernel_button_clicked), cw);
    g_signal_connect(btn_kernel6, "clicked", G_CALLBACK(on_kernel_button_clicked), cw);
    g_signal_connect(btn_kernel7, "clicked", G_CALLBACK(on_kernel_button_clicked), cw);

    g_signal_connect(btn_apply, "clicked", G_CALLBACK(on_apply_convolution), cw);

    gtk_widget_show(window);
}


//--------------------------------
// Setup da UI
//--------------------------------
void on_activate(GtkApplication* app, gpointer) {
    ImageState initial;

    std::string name;
    printf("Digite o nome do arquivo: ");
    std::getline(std::cin, name);  // lê até o enter

    const char* c_file_name = name.c_str();

    while (!load_image(c_file_name, initial)) {
        printf("Erro ao carregar a imagem!\n---------------------\n");

        printf("Digite o nome do arquivo: ");
        std::getline(std::cin, name);  // lê até o enter
        c_file_name = name.c_str();

    }

    original_data = (unsigned char*) malloc(initial.width * initial.height * 3);
    original_width = initial.width;
    original_height = initial.height;

    memcpy(original_data, initial.data, initial.width * initial.height * 3); 


    GtkWidget* win = gtk_application_window_new(app);
    GtkWidget* pic = gtk_picture_new();
    gtk_window_set_child(GTK_WINDOW(win), pic);

    gtk_widget_show(win);

    initial.picture = pic;
    initial.window = win;

    images.push_back(initial);

    update_picture(images.back());

    g_signal_connect(win, "destroy", G_CALLBACK(on_image_window_close), app);


    // janela de opções
    GtkWidget* control = gtk_application_window_new(app);
    gtk_window_set_title(GTK_WINDOW(control), "Operações");

    g_signal_connect(control, "destroy", G_CALLBACK(on_tools_window_close), app);

    GtkWidget* box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 5);

    GtkWidget* btn_copy = gtk_button_new_with_label("Copiar");
    g_signal_connect(btn_copy, "clicked", G_CALLBACK(on_copy), app);


    GtkWidget* btn_load = gtk_button_new_with_label("Carregar Nova Imagem");
    g_signal_connect(btn_load , "clicked", G_CALLBACK(on_load_new_image), app);


    GtkWidget* btn_gray = gtk_button_new_with_label("Escala de Cinza");
    g_signal_connect(btn_gray, "clicked", G_CALLBACK(on_gray), nullptr);

    GtkWidget* btn_h = gtk_button_new_with_label("Flip Horizontal");
    g_signal_connect(btn_h, "clicked", G_CALLBACK(on_flip_h), nullptr);

    GtkWidget* btn_v = gtk_button_new_with_label("Flip Vertical");
    g_signal_connect(btn_v, "clicked", G_CALLBACK(on_flip_v), nullptr);

    GtkWidget* btn_save = gtk_button_new_with_label("Salvar");
    g_signal_connect(btn_save, "clicked", G_CALLBACK(on_save), nullptr);

    GtkWidget* spin = gtk_spin_button_new_with_range(1, 256, 1);
    GtkWidget* btn_quant = gtk_button_new_with_label("Quantizar");
    g_signal_connect(btn_quant, "clicked", G_CALLBACK(on_quantize), spin);

    GtkWidget* btn_reset = gtk_button_new_with_label("Resetar");
    g_signal_connect(btn_reset, "clicked", G_CALLBACK(on_reset), nullptr);

    GtkWidget* btn_hist = gtk_button_new_with_label("Calcular Histograma");
    g_signal_connect(btn_hist, "clicked", G_CALLBACK(on_histogram_button_clicked), nullptr);

    GtkWidget* btn_negative = gtk_button_new_with_label("Aplicar Negativo");
    g_signal_connect(btn_negative, "clicked", G_CALLBACK(on_apply_negative), nullptr);

    GtkWidget* btn_equalize = gtk_button_new_with_label("Equalizar Histograma");
    g_signal_connect(btn_equalize, "clicked", G_CALLBACK(on_equalize_histogram), nullptr);

    GtkWidget* btn_hist_matching = gtk_button_new_with_label("Matching de Histograma");
    g_signal_connect(btn_hist_matching, "clicked", G_CALLBACK(on_hist_matching), nullptr);

    GtkWidget* btn_zoom_in = gtk_button_new_with_label("Zoom In");
    g_signal_connect(btn_zoom_in, "clicked", G_CALLBACK(on_zoom_in), nullptr);

    GtkWidget* btn_zoom_out = gtk_button_new_with_label("Zoom Out");

    GtkWidget* spin_sx = gtk_spin_button_new_with_range(1, G_MAXDOUBLE, 1);
    gtk_spin_button_set_value(GTK_SPIN_BUTTON(spin_sx), 2);

    GtkWidget* spin_sy = gtk_spin_button_new_with_range(1, G_MAXDOUBLE, 1);
    gtk_spin_button_set_value(GTK_SPIN_BUTTON(spin_sy), 2);

    gtk_widget_set_tooltip_text(spin_sx, "Digite o valor para o tamanho do retângulo no eixo X");
    gtk_widget_set_tooltip_text(spin_sy, "Digite o valor para o tamanho do retângulo no eixo Y");


    TwoSpins* spins_zoom_out = g_new(TwoSpins, 1); // aloca na heap
    spins_zoom_out->spin_a = (GtkWidget*) GTK_SPIN_BUTTON(spin_sx);
    spins_zoom_out->spin_b = (GtkWidget*) GTK_SPIN_BUTTON(spin_sy);

    g_signal_connect(btn_zoom_out, "clicked", G_CALLBACK(on_zoom_out), spins_zoom_out);


    GtkWidget* btn_rotate_90_clockise = gtk_button_new_with_label("Rotacionar 90° Horário");
    g_signal_connect(btn_rotate_90_clockise, "clicked", G_CALLBACK(on_rotate_90_clockise), nullptr);

    GtkWidget* btn_rotate_90_counterclockise = gtk_button_new_with_label("Rotacionar 90° Anti-Horário");
    g_signal_connect(btn_rotate_90_counterclockise, "clicked", G_CALLBACK(on_rotate_90_counterclockise), nullptr);


    GtkWidget* spin_brightness = gtk_spin_button_new_with_range(-255, 255, 1);
    gtk_spin_button_set_value(GTK_SPIN_BUTTON(spin_brightness), 127);
    GtkWidget* btn_brightness = gtk_button_new_with_label("Ajustar Brilho");
    g_signal_connect(btn_brightness, "clicked", G_CALLBACK(on_adjust_brightness), spin_brightness);

    GtkWidget* entry_contrast = gtk_entry_new();
    gtk_entry_set_placeholder_text(GTK_ENTRY(entry_contrast), "Digite um valor > 0.0");
    GtkWidget* btn_contrast = gtk_button_new_with_label("Ajustar Contraste");
    g_signal_connect(btn_contrast, "clicked", G_CALLBACK(on_adjust_contrast), entry_contrast);

    gtk_box_append(GTK_BOX(box), btn_copy);
    gtk_box_append(GTK_BOX(box), btn_load);
    gtk_box_append(GTK_BOX(box), btn_save);

    gtk_box_append(GTK_BOX(box), btn_gray);
    gtk_box_append(GTK_BOX(box), btn_h);
    gtk_box_append(GTK_BOX(box), btn_v);
    gtk_box_append(GTK_BOX(box), btn_hist);
    gtk_box_append(GTK_BOX(box), btn_negative);
    gtk_box_append(GTK_BOX(box), btn_equalize);
    gtk_box_append(GTK_BOX(box), btn_hist_matching);
    gtk_box_append(GTK_BOX(box), btn_zoom_in);

    GtkWidget* hbox_zoom_out = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(hbox_zoom_out), spin_sx);
    gtk_box_append(GTK_BOX(hbox_zoom_out), spin_sy);
    gtk_box_append(GTK_BOX(hbox_zoom_out), btn_zoom_out);
    gtk_box_append(GTK_BOX(box), hbox_zoom_out);

    GtkWidget* hbox_brightness = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(hbox_brightness), spin_brightness);
    gtk_box_append(GTK_BOX(hbox_brightness), btn_brightness);
    gtk_box_append(GTK_BOX(box), hbox_brightness);

    GtkWidget* hbox_contrast = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(hbox_contrast), entry_contrast);
    gtk_box_append(GTK_BOX(hbox_contrast), btn_contrast);
    gtk_box_append(GTK_BOX(box), hbox_contrast);

    GtkWidget* hbox_rotate = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(hbox_rotate), btn_rotate_90_clockise);
    gtk_box_append(GTK_BOX(hbox_rotate), btn_rotate_90_counterclockise);
    gtk_box_append(GTK_BOX(box), hbox_rotate);

    GtkWidget* hbox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_append(GTK_BOX(hbox), spin);
    gtk_box_append(GTK_BOX(hbox), btn_quant);

    gtk_box_append(GTK_BOX(box), hbox);
    gtk_box_append(GTK_BOX(box), btn_reset);


    gtk_window_set_child(GTK_WINDOW(control), box);
    gtk_widget_show(control);


    create_convolution_window(app);
}


void close_application(GtkApplication* app) {

    free(original_data);
    original_data = nullptr;

    if(images.size() > 0)
        images.clear();

    
    g_application_quit(G_APPLICATION(app));
}

void on_image_window_close(GtkWidget* widget, gpointer app_ptr) {
    GtkWidget* win = widget;
    GtkApplication* app = GTK_APPLICATION(app_ptr);

    for(int i = 0; i < images.size(); i++){
        if(images[i].window == win){
            free(images[i].data);
            images.erase(images.begin() + i);
            break;
        }
    }

    if(images.empty())
        close_application(app);
}


void on_tools_window_close(GtkWidget* widget, gpointer app_ptr) {
    GtkApplication* app = GTK_APPLICATION(app_ptr);
    close_application(app);
}

//--------------------------------
// main
//--------------------------------
int main(int argc, char** argv) {
    GtkApplication* app = gtk_application_new("org.exemplo.editor", G_APPLICATION_FLAGS_NONE);
    g_signal_connect(app, "activate", G_CALLBACK(on_activate), nullptr);
    int status = g_application_run(G_APPLICATION(app), argc, argv);
    g_object_unref(app);
    return status;
}
