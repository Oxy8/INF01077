#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

#include <iostream>
#include <vector>
#include <cstdlib>
#include <ctime>

const int WIDTH = 256;
const int HEIGHT = 256;
const int CHANNELS = 3;

// Função auxiliar para preencher um pixel RGB
void set_pixel(std::vector<unsigned char>& img, int x, int y, unsigned char r, unsigned char g, unsigned char b) {
    int idx = (y * WIDTH + x) * CHANNELS;
    img[idx] = r;
    img[idx + 1] = g;
    img[idx + 2] = b;
}

// 1. Ruído Puro (Mata o dynamic, 1)
void gerar_ruido_puro() {
    std::vector<unsigned char> img(WIDTH * HEIGHT * CHANNELS);
    for (size_t i = 0; i < img.size(); ++i) {
        img[i] = rand() % 256;
    }
    stbi_write_png("images/adv_01_ruido_puro.png", WIDTH, HEIGHT, CHANNELS, img.data(), WIDTH * CHANNELS);
    std::cout << "Criado: adv_01_ruido_puro.png" << std::endl;
}

// 2. Metade Lisa / Metade Ruído (Mata o static e chunks gigantes)
void gerar_meio_a_meio() {
    std::vector<unsigned char> img(WIDTH * HEIGHT * CHANNELS);
    for (int y = 0; y < HEIGHT; ++y) {
        bool is_white = y < HEIGHT / 2;
        for (int x = 0; x < WIDTH; ++x) {
            if (is_white) {
                set_pixel(img, x, y, 255, 255, 255);
            } else {
                unsigned char v = rand() % 256;
                set_pixel(img, x, y, v, v, v);
            }
        }
    }
    stbi_write_png("images/adv_02_meio_a_meio.png", WIDTH, HEIGHT, CHANNELS, img.data(), WIDTH * CHANNELS);
    std::cout << "Criado: adv_02_meio_a_meio.png" << std::endl;
}

// 3. Bandas Alternadas de 256 linhas (Destrói o dynamic, 256)
void gerar_bandas_256() {
    std::vector<unsigned char> img(WIDTH * HEIGHT * CHANNELS);
    int band_size = 256;
    for (int y = 0; y < HEIGHT; ++y) {
        bool is_white = (y / band_size) % 2 == 0;
        for (int x = 0; x < WIDTH; ++x) {
            if (is_white) {
                set_pixel(img, x, y, 255, 255, 255);
            } else {
                unsigned char v = rand() % 256;
                set_pixel(img, x, y, v, v, v);
            }
        }
    }
    stbi_write_png("images/adv_03_bandas_256.png", WIDTH, HEIGHT, CHANNELS, img.data(), WIDTH * CHANNELS);
    std::cout << "Criado: adv_03_bandas_256.png" << std::endl;
}

// 4. Liso Puro (Testa overhead desnecessário)
void gerar_branco_puro() {
    std::vector<unsigned char> img(WIDTH * HEIGHT * CHANNELS, 255);
    stbi_write_png("images/adv_04_branco_puro.png", WIDTH, HEIGHT, CHANNELS, img.data(), WIDTH * CHANNELS);
    std::cout << "Criado: adv_04_branco_puro.png" << std::endl;
}

int main() {
    srand(static_cast<unsigned int>(time(nullptr)));
    
    std::cout << "Gerando imagens adversárias em 6000x6000. Isso pode demorar alguns segundos..." << std::endl;
    
    // Garante que a pasta images existe
    system("mkdir -p images");

    gerar_ruido_puro();
    gerar_meio_a_meio();
    gerar_bandas_256();
    gerar_branco_puro();

    std::cout << "Todas as imagens foram geradas com sucesso na pasta 'images/'!" << std::endl;
    return 0;
}