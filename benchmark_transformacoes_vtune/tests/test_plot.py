import importlib.util
import math
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "plot.py"
SPEC = importlib.util.spec_from_file_location("vtune_plot", MODULE_PATH)
plot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(plot)


class PlotTest(unittest.TestCase):
    def test_hardware_events_are_normalized_by_workload_iterations(self):
        rows = []
        for schedule, iterations, multiplier in (
            ("static", 2, 1.0),
            ("dynamic_1", 4, 3.0),
        ):
            for share in (0.25, 0.75):
                row = {
                    "Num_Threads": 40,
                    "OMP_Schedule": schedule,
                    "Transformation": "Zoom_In",
                    "Workload_Iterations": iterations,
                }
                for name, column in plot.COLUNAS_EVENTOS_HW.items():
                    baseline_per_iteration = 100.0 if name != "Instructions" else 1000.0
                    row[column] = (
                        baseline_per_iteration * iterations * multiplier * share
                    )
                rows.append(row)

        result = plot.agregar_eventos_hardware(pd.DataFrame(rows))
        static = result[result["OMP_Schedule"].eq("static")].iloc[0]
        dynamic = result[result["OMP_Schedule"].eq("dynamic_1")].iloc[0]

        self.assertAlmostEqual(static["L1_Pending_Cycles_por_iteracao"], 100.0)
        self.assertAlmostEqual(dynamic["L1_Pending_Cycles_por_iteracao"], 300.0)
        self.assertAlmostEqual(
            static["CPU_Clock_Unhalted_Thread_por_iteracao"], 100.0
        )
        self.assertAlmostEqual(
            dynamic["CPU_Clock_Unhalted_Thread_por_iteracao"], 300.0
        )
        self.assertAlmostEqual(dynamic["Fator_L1_Pending_Cycles"], 3.0)
        self.assertAlmostEqual(dynamic["Fator_Instructions"], 3.0)

    def test_speedup_decomposition_survives_equal_weight_image_normalization(self):
        rows = []
        values = {
            ("a.png", "static"): (10.0, 0.10, 10.0),
            ("a.png", "dynamic_1"): (5.0, 0.08, 16.0),
            ("b.png", "static"): (20.0, 0.20, 10.0),
            ("b.png", "dynamic_1"): (40.0, 0.10, 2.5),
        }
        for (image, schedule), (wall_ms, cpu_time, active_cores) in values.items():
            rows.append(
                {
                    "Num_Threads": 20,
                    "OMP_Schedule": schedule,
                    "Transformation": "Synthetic",
                    "Image": image,
                    "Mediana_ms": wall_ms,
                    "Media_ms": wall_ms,
                    "CPU_Time_por_chamada": cpu_time,
                    "Instrucoes_por_chamada": 1000.0,
                    "Nucleos_ativos": active_cores,
                    "CPI_Rate": 1.0,
                    "Average_CPU_Frequency": 2.5e9,
                    "Baixa_utilizacao_Percent": 10.0,
                    "Memory_Bound_Percent": 20.0,
                    "Memory_Bound_L1_Bound_Percent": 5.0,
                    "Memory_Bound_Store_Bound_Percent": 2.0,
                    "Cobertura_Percent": 100.0,
                }
            )

        summary = plot.resumir_condicoes(pd.DataFrame(rows))
        dynamic = summary[summary["OMP_Schedule"].eq("dynamic_1")].iloc[0]

        # One image gains 2x and the other loses 2x, so equal-weight geometric
        # normalization reports 1x overall.
        self.assertAlmostEqual(dynamic["VTune_Speedup_Perfil"], 1.0)
        self.assertAlmostEqual(dynamic["Fator_Trabalho_CPU"], math.sqrt(2.5))
        self.assertAlmostEqual(dynamic["Fator_Paralelismo"], math.sqrt(0.4))
        self.assertAlmostEqual(
            dynamic["VTune_Speedup_Perfil"],
            dynamic["Fator_Trabalho_CPU"] * dynamic["Fator_Paralelismo"],
        )
        self.assertLess(dynamic["Erro_Decomposicao"], 1e-12)

    def test_schedule_order_is_numeric(self):
        schedules = ["dynamic_1024", "dynamic_2", "static", "dynamic_16"]
        self.assertEqual(
            sorted(schedules, key=plot.ordem_schedule),
            ["static", "dynamic_2", "dynamic_16", "dynamic_1024"],
        )


if __name__ == "__main__":
    unittest.main()
