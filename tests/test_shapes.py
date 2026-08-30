from snip_occlusion import shapes as sh


def make(kind="rect", x=0, y=0, w=10, h=10, group=None, **kw):
    return sh.Shape(kind=kind, x=x, y=y, w=w, h=h, group=group, **kw)


def test_contains_rect_and_ellipse():
    r = make(x=10, y=10, w=20, h=10)
    assert r.contains(10, 10) and r.contains(30, 20)
    assert not r.contains(31, 20)
    e = make(kind="ellipse", x=0, y=0, w=20, h=20)
    assert e.contains(10, 10)  # centre
    assert not e.contains(1, 1)  # corner outside the ellipse


def test_target_groups_one_card_per_group_in_order():
    a = make(group="g1")
    b = make(group=None)
    c = make(group="g1")
    d = make(group="g2")
    erase = make(kind="erase")
    groups = sh.target_groups([a, b, c, d, erase])
    assert groups == ["g1", "s:" + b.id, "g2"]


def test_arbitrary_grouping_can_skip_middle_box():
    # the IOE limitation this add-on fixes: top and bottom grouped,
    # middle box stays its own card
    top = make(y=0, group="g1")
    middle = make(y=20)
    bottom = make(y=40, group="g1")
    groups = sh.target_groups([top, middle, bottom])
    assert groups == ["g1", "s:" + middle.id]


def test_normalized_payload_excludes_erase_and_rounds():
    s = make(x=100, y=50, w=200, h=25, group="g1")
    e = make(kind="erase", x=0, y=0, w=10, h=10, color="#fbf3e4")
    payload = sh.normalized_payload([s, e], 800, 500)
    assert len(payload["shapes"]) == 1
    p = payload["shapes"][0]
    assert p["x"] == 0.125 and p["y"] == 0.1
    assert p["w"] == 0.25 and p["h"] == 0.05
    assert p["group"] == "g1"


def test_serialize_roundtrip():
    orig = [
        make(group="g1"),
        make(kind="erase", color="#ffffff"),
        make(kind="patch", x=50, y=200, w=80, h=20, sx=50, sy=30),
    ]
    restored = sh.deserialize(sh.serialize(orig))
    assert [s.to_dict() for s in restored] == [s.to_dict() for s in orig]
    assert restored[2].sx == 50 and restored[2].sy == 30


def test_patches_are_not_masks_and_layer_below_them():
    mask = make()
    erase = make(kind="erase")
    patch = make(kind="patch", sx=0, sy=0)
    shapes = [mask, erase, patch]
    assert sh.mask_shapes(shapes) == [mask]
    assert sh.patch_shapes(shapes) == [patch]
    assert sh.target_groups(shapes) == ["s:" + mask.id]
    assert sh.layer_of(erase) < sh.layer_of(patch) < sh.layer_of(mask)
    payload = sh.normalized_payload(shapes, 100, 100)
    assert len(payload["shapes"]) == 1


def test_clamp_rect():
    assert sh.clamp_rect(-5, -5, 10, 10, 100, 100) == (0, 0, 10, 10)
    assert sh.clamp_rect(95, 95, 10, 10, 100, 100) == (90, 90, 10, 10)
    x, y, w, h = sh.clamp_rect(0, 0, 200, 50, 100, 100)
    assert w == 100
