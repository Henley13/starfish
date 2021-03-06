"""
These tests center around creating an ImageStack with labeled indices and verifying that operations
on such an ImageStack work.
"""
from typing import Mapping, Tuple, Union

import numpy as np
from slicedimage import ImageFormat

from starfish.experiment.builder import build_image, FetchedTile, tile_fetcher_factory
from starfish.imagestack.imagestack import ImageStack
from starfish.types import Axes, Coordinates, Number
from .imagestack_test_utils import verify_physical_coordinates, verify_stack_fill

ROUND_LABELS = (1, 4, 6)
CH_LABELS = (2, 4, 6, 8)
ZPLANE_LABELS = (3, 4)
HEIGHT = 2
WIDTH = 4

NUM_ROUND = len(ROUND_LABELS)
NUM_CH = len(CH_LABELS)
NUM_Z = len(ZPLANE_LABELS)


def fill_value(round_: int, ch: int, z: int) -> float:
    """Return the expected fill value for a given tile."""
    round_idx = ROUND_LABELS.index(round_)
    ch_idx = CH_LABELS.index(ch)
    z_idx = ZPLANE_LABELS.index(z)
    return float((((round_idx * NUM_CH) + ch_idx) * NUM_Z) + z_idx) / (NUM_ROUND * NUM_CH * NUM_Z)


def x_coordinates(round_: int, ch: int) -> Tuple[float, float]:
    """Return the expected physical x coordinate value for a given round/ch tuple.  Note that in
    real life, physical coordinates are not expected to vary for different ch values.  However, for
    completeness of the tests, we are pretending they will."""
    return min(round_, ch) * 0.01, max(round_, ch) * 0.01


def y_coordinates(round_: int, ch: int) -> Tuple[float, float]:
    """Return the expected physical y coordinate value for a given round/ch tuple.  Note that in
    real life, physical coordinates are not expected to vary for different ch values.  However, for
    completeness of the tests, we are pretending they will."""
    return min(round_, ch) * 0.001, max(round_, ch) * 0.001


def z_coordinates(z: int) -> Tuple[float, float]:
    """Return the expected physical z coordinate value for a given zplane index."""
    return z * 0.0001, (z + 1) * 0.0001


class UniqueTiles(FetchedTile):
    """Tiles where the pixel values are unique per round/ch/z."""
    def __init__(self, fov: int, _round: int, ch: int, zplane: int) -> None:
        super().__init__()
        self._round = _round
        self._ch = ch
        self._zplane = zplane

    @property
    def shape(self) -> Tuple[int, ...]:
        return HEIGHT, WIDTH

    @property
    def coordinates(self) -> Mapping[Union[str, Coordinates], Union[Number, Tuple[Number, Number]]]:
        return {
            Coordinates.X: x_coordinates(self._round, self._ch),
            Coordinates.Y: y_coordinates(self._round, self._ch),
            Coordinates.Z: z_coordinates(self._zplane),
        }

    @property
    def format(self) -> ImageFormat:
        return ImageFormat.TIFF

    def tile_data(self) -> np.ndarray:
        return np.full(
            shape=(HEIGHT, WIDTH),
            fill_value=fill_value(self._round, self._ch, self._zplane),
            dtype=np.float32)


def setup_imagestack() -> ImageStack:
    """Build an imagestack with labeled indices (i.e., indices that do not start at 0 or are not
    sequential non-negative integers).
    """
    collection = build_image(
        range(1),
        ROUND_LABELS,
        CH_LABELS,
        ZPLANE_LABELS,
        tile_fetcher_factory(UniqueTiles, True),
    )
    tileset = list(collection.all_tilesets())[0][1]

    return ImageStack.from_tileset(tileset)


def test_labeled_indices_read():
    """Build an imagestack with labeled indices (i.e., indices that do not start at 0 or are not
    sequential non-negative integers).  Verify that get_slice behaves correctly.
    """
    stack = setup_imagestack()

    for round_ in stack.axis_labels(Axes.ROUND):
        for ch in stack.axis_labels(Axes.CH):
            for zplane in stack.axis_labels(Axes.ZPLANE):
                verify_stack_fill(
                    stack,
                    {Axes.ROUND: round_, Axes.CH: ch, Axes.ZPLANE: zplane},
                    fill_value(round_, ch, zplane),
                )


def test_labeled_indices_set_slice():
    """Build an imagestack with labeled indices (i.e., indices that do not start at 0 or are not
    sequential non-negative integers).  Verify that set_slice behaves correctly.
    """
    for round_ in ROUND_LABELS:
        for ch in CH_LABELS:
            for zplane in ZPLANE_LABELS:
                stack = setup_imagestack()
                zeros = np.zeros((HEIGHT, WIDTH), dtype=np.float32)

                stack.set_slice(
                    {Axes.ROUND: round_, Axes.CH: ch, Axes.ZPLANE: zplane}, zeros)

                for selector in stack._iter_axes({Axes.ROUND, Axes.CH, Axes.ZPLANE}):
                    if (selector[Axes.ROUND] == round_
                            and selector[Axes.CH] == ch
                            and selector[Axes.ZPLANE] == zplane):
                        expected_fill_value = 0
                    else:
                        expected_fill_value = fill_value(
                            selector[Axes.ROUND], selector[Axes.CH], selector[Axes.ZPLANE])

                    verify_stack_fill(stack, selector, expected_fill_value)


def test_labeled_indices_sel_single_tile():
    """Select a single tile across each index from an ImageStack with labeled indices.  Verify that
    the data is correct and that the physical coordinates are correctly set."""
    stack = setup_imagestack()

    for selector in stack._iter_axes({Axes.ROUND, Axes.CH, Axes.ZPLANE}):
        subselected = stack.sel(selector)

        # verify that the subselected stack has the correct index labels.
        for index_type in (Axes.ROUND, Axes.CH, Axes.ZPLANE):
            assert subselected.axis_labels(index_type) == [selector[index_type]]

        # verify that the subselected stack has the correct data.
        expected_fill_value = fill_value(
            selector[Axes.ROUND], selector[Axes.CH], selector[Axes.ZPLANE])
        verify_stack_fill(stack, selector, expected_fill_value)

        # verify that the subselected stack has the correct size for the physical coordinates table.
        sizes = subselected.coordinates.sizes
        for dim in (Axes.ROUND.value, Axes.CH.value, Axes.ZPLANE.value):
            assert sizes[dim] == 1

        # assert that the physical coordinate values are what we expect.
        verify_physical_coordinates(
            stack,
            selector,
            x_coordinates(selector[Axes.ROUND], selector[Axes.CH]),
            y_coordinates(selector[Axes.ROUND], selector[Axes.CH]),
            z_coordinates(selector[Axes.ZPLANE]),
        )


def test_labeled_indices_sel_slice():
    """Select a single tile across each index from an ImageStack with labeled indices.  Verify that
    the data is correct and that the physical coordinates are correctly set."""
    stack = setup_imagestack()
    selector = {Axes.ROUND: slice(None, 4), Axes.CH: slice(4, 6), Axes.ZPLANE: 4}
    subselected = stack.sel(selector)

    # verify that the subselected stack has the correct index labels.
    for index_type, expected_results in (
            (Axes.ROUND, [1, 4]),
            (Axes.CH, [4, 6]),
            (Axes.ZPLANE, [4],)):
        assert subselected.axis_labels(index_type) == expected_results

    # verify that the subselected stack has the correct size for the physical coordinates table.
    sizes = subselected.coordinates.sizes
    assert sizes[Axes.ROUND] == 2
    assert sizes[Axes.CH] == 2
    assert sizes[Axes.ZPLANE] == 1

    for selectors in subselected._iter_axes({Axes.ROUND, Axes.CH, Axes.ZPLANE}):
        # verify that the subselected stack has the correct data.
        expected_fill_value = fill_value(
            selectors[Axes.ROUND], selectors[Axes.CH], selectors[Axes.ZPLANE])
        verify_stack_fill(subselected, selectors, expected_fill_value)

        # verify that each tile in the subselected stack has the correct physical coordinates.
        verify_physical_coordinates(
            stack,
            selectors,
            x_coordinates(selectors[Axes.ROUND], selectors[Axes.CH]),
            y_coordinates(selectors[Axes.ROUND], selectors[Axes.CH]),
            z_coordinates(selectors[Axes.ZPLANE]),
        )
