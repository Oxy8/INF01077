#include <iostream>
#include <vector>
#include <omp.h>

int main() {
    std::cout << "Iniciando Teste HPC-Performance..." << std::endl;
    
    // Aloca 3 vetores de aproximadamente 400 MB cada (total ~1.2 GB)
    const size_t N = 100000000;
    std::vector<float> a(N, 1.5f);
    std::vector<float> b(N, 2.5f);
    std::vector<float> c(N, 0.0f);

    // Repete 50 vezes para garantir que o programa demore uns 3 a 5 segundos,
    // tempo suficiente para o VTune calibrar e coletar as amostras.
    for (int iter = 0; iter < 50; ++iter) {
        
        #pragma omp parallel for simd schedule(static)
        for (size_t i = 0; i < N; ++i) {
            // Conta matemática clássica FMA (Fused Multiply-Add)
            c[i] = a[i] + b[i] * 3.14159f;
        }
    }

    std::cout << "Teste concluído com sucesso. Amostra [0]: " << c[0] << std::endl;
    return 0;
}
