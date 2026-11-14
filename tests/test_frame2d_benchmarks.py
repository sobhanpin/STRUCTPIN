"""Closed-form benchmark tests for the 2D frame solver.

Run from the STRUCTPIN folder (see DEVELOPMENT_STATUS.md).
"""

import math
import unittest

from structpin.model.structural_model import StructuralModel, ModelError
from structpin.fem.frame2d import solve_frame
from structpin.fem.linalg import solve_dense, SingularSystemError

E = 200.0
A = 0.01
I = 2e-4


def _base_model():
    m = StructuralModel("benchmark")
    m.add_material("steel", E)
    m.add_section("sec", A, I)
    return m


class LinearSolverTest(unittest.TestCase):
    def test_known_2x2_system(self):
        x = solve_dense([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0])
        self.assertAlmostEqual(x[0], 0.8, places=12)
        self.assertAlmostEqual(x[1], 1.4, places=12)

    def test_singular_matrix_raises(self):
        with self.assertRaises(SingularSystemError):
            solve_dense([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])


class CantileverTest(unittest.TestCase):
    L = 2.0
    P = 10.0

    def setUp(self):
        m = _base_model()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, self.L, 0.0)
        m.add_member(1, 1, 2, "steel", "sec")
        m.add_restraint(1, ux=True, uy=True, rz=True)
        m.add_nodal_load(2, fy=-self.P)
        self.results = solve_frame(m)

    def test_tip_deflection_matches_closed_form(self):
        uy = self.results.displacements[2][1]
        expected = -self.P * self.L ** 3 / (3 * E * I)
        self.assertTrue(math.isclose(uy, expected, rel_tol=1e-9))

    def test_tip_rotation_matches_closed_form(self):
        rz = self.results.displacements[2][2]
        expected = -self.P * self.L ** 2 / (2 * E * I)
        self.assertTrue(math.isclose(rz, expected, rel_tol=1e-9))

    def test_base_reactions_balance_load(self):
        rx, ry, mz = self.results.reactions[1]
        self.assertTrue(math.isclose(ry, self.P, rel_tol=1e-9))
        self.assertTrue(math.isclose(mz, self.P * self.L, rel_tol=1e-9))
        self.assertAlmostEqual(rx, 0.0, places=9)


class SimplySupportedPointLoadTest(unittest.TestCase):
    def test_midspan_deflection_matches_closed_form(self):
        L = 4.0
        P = 10.0
        m = _base_model()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, L / 2, 0.0)
        m.add_node(3, L, 0.0)
        m.add_member(1, 1, 2, "steel", "sec")
        m.add_member(2, 2, 3, "steel", "sec")
        m.add_restraint(1, ux=True, uy=True)
        m.add_restraint(3, uy=True)
        m.add_nodal_load(2, fy=-P)
        r = solve_frame(m)
        expected = -P * L ** 3 / (48 * E * I)
        self.assertTrue(math.isclose(r.displacements[2][1], expected, rel_tol=1e-9))


class SimplySupportedUniformLoadTest(unittest.TestCase):
    def test_end_rotation_matches_closed_form(self):
        L = 3.0
        q = -4.0  # downward
        m = _base_model()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, L, 0.0)
        m.add_member(1, 1, 2, "steel", "sec")
        m.add_restraint(1, ux=True, uy=True)
        m.add_restraint(2, uy=True)
        m.add_member_udl(1, q)
        r = solve_frame(m)
        expected = q * L ** 3 / (24 * E * I)
        self.assertTrue(math.isclose(r.displacements[1][2], expected, rel_tol=1e-9))
        self.assertTrue(math.isclose(r.reactions[1][1] + r.reactions[2][1], -q * L, rel_tol=1e-9))


class PortalFrameEquilibriumTest(unittest.TestCase):
    def test_global_equilibrium_under_lateral_load(self):
        H = 10.0
        m = _base_model()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, 0.0, 3.0)
        m.add_node(3, 4.0, 3.0)
        m.add_node(4, 4.0, 0.0)
        m.add_member(1, 1, 2, "steel", "sec")
        m.add_member(2, 2, 3, "steel", "sec")
        m.add_member(3, 4, 3, "steel", "sec")
        m.add_restraint(1, ux=True, uy=True, rz=True)
        m.add_restraint(4, ux=True, uy=True, rz=True)
        m.add_nodal_load(2, fx=H)
        r = solve_frame(m)
        sum_rx = r.reactions[1][0] + r.reactions[4][0]
        sum_ry = r.reactions[1][1] + r.reactions[4][1]
        self.assertTrue(math.isclose(sum_rx, -H, rel_tol=1e-9))
        self.assertAlmostEqual(sum_ry, 0.0, places=9)


class ValidationTest(unittest.TestCase):
    def test_unsupported_model_is_reported_as_unstable(self):
        m = _base_model()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, 2.0, 0.0)
        m.add_member(1, 1, 2, "steel", "sec")
        m.add_nodal_load(2, fy=-1.0)
        with self.assertRaises(SingularSystemError):
            solve_frame(m)

    def test_duplicate_member_is_rejected(self):
        m = _base_model()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, 2.0, 0.0)
        m.add_member(1, 1, 2, "steel", "sec")
        m.add_member(2, 2, 1, "steel", "sec")
        m.add_restraint(1, ux=True, uy=True, rz=True)
        with self.assertRaises(ModelError):
            solve_frame(m)


if __name__ == "__main__":
    unittest.main()
