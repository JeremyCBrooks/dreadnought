"""Tests for graph-based galaxy generation."""
from world.galaxy import Galaxy


def _direction(sys_a, sys_b):
    """Return the (dx, dy) direction snapped to 8 cardinal/diagonal."""
    dx = sys_b.gx - sys_a.gx
    dy = sys_b.gy - sys_a.gy
    # Normalize to -1/0/1
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    return (sx, sy)


class TestGalaxyGraph:
    def test_all_systems_have_grid_positions(self):
        g = Galaxy(seed=1)
        for sys in g.systems.values():
            assert hasattr(sys, "gx")
            assert hasattr(sys, "gy")
            assert isinstance(sys.gx, int)
            assert isinstance(sys.gy, int)

    def test_no_two_systems_share_position(self):
        for seed in range(10):
            g = Galaxy(seed=seed)
            positions = [(s.gx, s.gy) for s in g.systems.values()]
            assert len(positions) == len(set(positions)), f"Duplicate positions with seed={seed}"

    def test_all_systems_reachable(self):
        """BFS from home should reach every system."""
        for seed in range(10):
            g = Galaxy(seed=seed)
            visited = set()
            queue = [g.home_system]
            visited.add(g.home_system)
            while queue:
                name = queue.pop(0)
                for neighbor in g.systems[name].connections:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            assert visited == set(g.systems.keys()), f"Disconnected graph with seed={seed}"

    def test_connections_are_bidirectional(self):
        g = Galaxy(seed=1)
        for name, sys in g.systems.items():
            for neighbor, fuel in sys.connections.items():
                assert name in g.systems[neighbor].connections, (
                    f"{name} -> {neighbor} but not reverse"
                )

    def test_no_direction_conflicts(self):
        """Each system should have at most one connection per direction."""
        for seed in range(10):
            g = Galaxy(seed=seed)
            for name, sys in g.systems.items():
                directions_used = set()
                for neighbor in sys.connections:
                    d = _direction(sys, g.systems[neighbor])
                    assert d not in directions_used, (
                        f"seed={seed}: {name} has two connections in direction {d}"
                    )
                    assert d != (0, 0), f"Connection to self-position"
                    directions_used.add(d)

    def test_depth_based_on_graph_distance(self):
        """Depth should equal BFS distance from home."""
        g = Galaxy(seed=1)
        # BFS from home
        distances = {g.home_system: 0}
        queue = [g.home_system]
        while queue:
            name = queue.pop(0)
            for neighbor in g.systems[name].connections:
                if neighbor not in distances:
                    distances[neighbor] = distances[name] + 1
                    queue.append(neighbor)
        for name, sys in g.systems.items():
            assert sys.depth == distances[name], (
                f"{name}: depth={sys.depth} but BFS distance={distances[name]}"
            )

    def test_fuel_cost_positive(self):
        g = Galaxy(seed=1)
        for sys in g.systems.values():
            for fuel in sys.connections.values():
                assert fuel > 0

    def test_max_connections_per_system(self):
        """No system should have more than 8 connections."""
        for seed in range(10):
            g = Galaxy(seed=seed)
            for sys in g.systems.values():
                assert len(sys.connections) <= 8

    def test_same_seed_same_graph(self):
        g1 = Galaxy(seed=42)
        g2 = Galaxy(seed=42)
        assert set(g1.systems.keys()) == set(g2.systems.keys())
        for name in g1.systems:
            s1, s2 = g1.systems[name], g2.systems[name]
            assert s1.gx == s2.gx
            assert s1.gy == s2.gy
            assert s1.connections == s2.connections

    def test_edges_are_sparse(self):
        """With 10 nodes, MST has 9 edges. We add a few extras but stay sparse."""
        for seed in range(10):
            g = Galaxy(seed=seed)
            total_edges = sum(len(s.connections) for s in g.systems.values()) // 2
            n = len(g.systems)
            assert total_edges >= n - 1, "Fewer edges than MST"
            assert total_edges <= n + 4, f"seed={seed}: too many edges ({total_edges})"

    def test_fuel_cost_symmetric(self):
        """Fuel cost A->B should equal B->A."""
        g = Galaxy(seed=1)
        for name, sys in g.systems.items():
            for neighbor, fuel in sys.connections.items():
                reverse_fuel = g.systems[neighbor].connections[name]
                assert fuel == reverse_fuel, (
                    f"{name}->{neighbor} fuel={fuel} but reverse={reverse_fuel}"
                )

    def test_small_galaxy(self):
        """Galaxy with fewer than 10 systems should still work."""
        g = Galaxy(seed=1, num_systems=3)
        assert len(g.systems) == 3
        # Still fully connected
        visited = {g.home_system}
        queue = [g.home_system]
        while queue:
            name = queue.pop(0)
            for neighbor in g.systems[name].connections:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        assert visited == set(g.systems.keys())
