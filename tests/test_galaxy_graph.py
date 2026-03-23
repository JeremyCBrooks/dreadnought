"""Tests for graph-based galaxy generation."""

from world.galaxy import Galaxy


def _direction(sys_a, sys_b):
    """Return the (dx, dy) direction snapped to 8 cardinal/diagonal."""
    dx = sys_b.gx - sys_a.gx
    dy = sys_b.gy - sys_a.gy
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    return (sx, sy)


def _explore_n(g, max_systems=20):
    """BFS-explore up to max_systems systems, expanding frontiers."""
    explored = set()
    queue = [g.home_system]
    while queue and len(explored) < max_systems:
        name = queue.pop(0)
        if name in explored:
            continue
        explored.add(name)
        g.arrive_at(name)
        for neighbor in g.systems[name].connections:
            if neighbor not in explored:
                queue.append(neighbor)
    return explored


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
            _explore_n(g, 15)
            positions = [(s.gx, s.gy) for s in g.systems.values()]
            assert len(positions) == len(set(positions)), f"Duplicate positions with seed={seed}"

    def test_all_generated_systems_reachable(self):
        """BFS from home should reach every generated system."""
        for seed in range(10):
            g = Galaxy(seed=seed)
            _explore_n(g, 15)
            # BFS without expanding (just check connectivity)
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
        _explore_n(g, 15)
        for name, sys in g.systems.items():
            for neighbor, fuel in sys.connections.items():
                assert name in g.systems[neighbor].connections, f"{name} -> {neighbor} but not reverse"

    def test_no_direction_conflicts(self):
        """Each system should have at most one connection per direction."""
        for seed in range(10):
            g = Galaxy(seed=seed)
            _explore_n(g, 15)
            for name, sys in g.systems.items():
                directions_used = set()
                for neighbor in sys.connections:
                    d = _direction(sys, g.systems[neighbor])
                    assert d not in directions_used, f"seed={seed}: {name} has two connections in direction {d}"
                    assert d != (0, 0), "Connection to self-position"
                    directions_used.add(d)

    def test_depth_based_on_graph_distance(self):
        """Depth should equal BFS distance from home."""
        g = Galaxy(seed=1)
        _explore_n(g, 15)
        distances = {g.home_system: 0}
        queue = [g.home_system]
        while queue:
            name = queue.pop(0)
            for neighbor in g.systems[name].connections:
                if neighbor not in distances:
                    distances[neighbor] = distances[name] + 1
                    queue.append(neighbor)
        for name, sys in g.systems.items():
            assert sys.depth == distances[name], f"{name}: depth={sys.depth} but BFS distance={distances[name]}"

    def test_fuel_cost_positive(self):
        g = Galaxy(seed=1)
        _explore_n(g, 15)
        for sys in g.systems.values():
            for fuel in sys.connections.values():
                assert fuel > 0

    def test_max_connections_per_system(self):
        """No system should have more than 8 connections."""
        for seed in range(10):
            g = Galaxy(seed=seed)
            _explore_n(g, 15)
            for sys in g.systems.values():
                assert len(sys.connections) <= 8

    def test_same_seed_same_graph(self):
        """Same seed + same exploration path = same galaxy."""
        g1 = Galaxy(seed=42)
        g2 = Galaxy(seed=42)
        # Same state at init
        assert set(g1.systems.keys()) == set(g2.systems.keys())
        for name in g1.systems:
            s1, s2 = g1.systems[name], g2.systems[name]
            assert s1.gx == s2.gx
            assert s1.gy == s2.gy
            assert s1.connections == s2.connections
        # Explore same path
        home = g1.home_system
        neighbor = next(iter(g1.systems[home].connections))
        g1.arrive_at(neighbor)
        g2.arrive_at(neighbor)
        assert set(g1.systems.keys()) == set(g2.systems.keys())
        for name in g1.systems:
            assert g1.systems[name].connections == g2.systems[name].connections

    def test_fuel_cost_symmetric(self):
        """Fuel cost A->B should equal B->A."""
        g = Galaxy(seed=1)
        _explore_n(g, 15)
        for name, sys in g.systems.items():
            for neighbor, fuel in sys.connections.items():
                reverse_fuel = g.systems[neighbor].connections[name]
                assert fuel == reverse_fuel, f"{name}->{neighbor} fuel={fuel} but reverse={reverse_fuel}"

    def test_dead_ends_exist(self):
        """Some systems should be dead ends (only 1 connection) after exploration."""
        found_dead_end = False
        for seed in range(20):
            g = Galaxy(seed=seed)
            _explore_n(g, 15)
            for sys in g.systems.values():
                if len(sys.connections) == 1:
                    found_dead_end = True
                    break
            if found_dead_end:
                break
        assert found_dead_end, "Expected at least some dead ends across seeds"

    def test_branching_typical(self):
        """Most explored systems should have 2-4 connections."""
        g = Galaxy(seed=1)
        explored = _explore_n(g, 15)
        counts = [len(g.systems[n].connections) for n in explored]
        typical = sum(1 for c in counts if 2 <= c <= 4)
        assert typical >= len(counts) // 2, "Most explored systems should have 2-4 connections"

    def test_graph_always_grows(self):
        """Exploring should always produce new reachable systems (no closed graphs)."""
        for seed in range(20):
            g = Galaxy(seed=seed)
            for _ in range(10):
                # Find an unexplored frontier system
                unexplored = [
                    n for name in g.systems for n in g.systems[name].connections if n not in g._generated_frontiers
                ]
                if not unexplored:
                    break
                g.arrive_at(unexplored[0])
            # After 10 steps, there should still be unexplored frontier systems
            frontier = [n for name in g.systems for n in g.systems[name].connections if n not in g._generated_frontiers]
            assert len(frontier) > 0, f"seed={seed}: graph closed after exploration"

    def test_revisit_depths_still_correct(self):
        """Depths must remain correct after revisiting (when _assign_depths is skipped)."""
        g = Galaxy(seed=1)
        home_name = g.home_system
        neighbor_name = next(iter(g.systems[home_name].connections))
        g.arrive_at(neighbor_name)
        # Revisit home — should skip _assign_depths but depths stay correct
        g.arrive_at(home_name)
        # Verify depths via manual BFS
        distances = {home_name: 0}
        queue = [home_name]
        while queue:
            name = queue.pop(0)
            for nb in g.systems[name].connections:
                if nb not in distances:
                    distances[nb] = distances[name] + 1
                    queue.append(nb)
        for name, sys in g.systems.items():
            assert sys.depth == distances[name], f"{name}: depth={sys.depth} but BFS={distances[name]}"

    def test_backtracking_preserves(self):
        """Visiting a system, leaving, and returning preserves everything."""
        g = Galaxy(seed=1)
        home = g.systems[g.home_system]
        neighbor_name = next(iter(home.connections))
        g.arrive_at(neighbor_name)
        snapshot_connections = dict(g.systems[neighbor_name].connections)
        snapshot_locations = [loc.name for loc in g.systems[neighbor_name].locations]
        # Go back and return
        g.arrive_at(g.home_system)
        g.arrive_at(neighbor_name)
        assert dict(g.systems[neighbor_name].connections) == snapshot_connections
        assert [loc.name for loc in g.systems[neighbor_name].locations] == snapshot_locations
