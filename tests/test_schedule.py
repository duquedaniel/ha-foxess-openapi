import importlib.util, pathlib
p = pathlib.Path(__file__).parents[1] / "custom_components/foxess_openapi/schedule.py"
spec = importlib.util.spec_from_file_location("schedule", p); s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

def g(sh, sm, eh, em, mode="SelfUse", **kw):
    d = {"enable": 1, "startHour": sh, "startMinute": sm, "endHour": eh, "endMinute": em,
         "workMode": mode, "minSocOnGrid": 10, "fdSoc": 10, "fdPwr": 0, "maxSoc": 100}
    d.update(kw); return d

def spans(groups):
    return [(x["workMode"], f'{x["startHour"]:02d}:{x["startMinute"]:02d}', f'{x["endHour"]:02d}:{x["endMinute"]:02d}') for x in groups]

def test_selfuse_day_split_around_charge():
    out = s.merge_charge_groups([g(0,0,23,59)], [g(6,43,7,59,"ForceCharge",fdSoc=35,fdPwr=1500)])
    assert spans(out) == [("SelfUse","00:00","06:42"),("ForceCharge","06:43","07:59"),("SelfUse","08:00","23:59")]
    assert s.find_overlaps(out) == []
    assert out[1]["fdSoc"] == 35 and out[0]["fdSoc"] == 10

def test_charge_at_day_start_and_end():
    out = s.merge_charge_groups([g(0,0,23,59)], [g(0,0,1,0,"ForceCharge")])
    assert spans(out) == [("ForceCharge","00:00","01:00"),("SelfUse","01:01","23:59")]
    out = s.merge_charge_groups([g(0,0,23,59)], [g(23,0,23,59,"ForceCharge"), g(0,0,0,30,"ForceCharge")])
    assert spans(out) == [("ForceCharge","00:00","00:30"),("SelfUse","00:31","22:59"),("ForceCharge","23:00","23:59")]

def test_non_overlapping_kept_untouched():
    out = s.merge_charge_groups([g(12,0,14,0,"Feedin")], [g(6,0,7,59,"ForceCharge")])
    assert spans(out) == [("ForceCharge","06:00","07:59"),("Feedin","12:00","14:00")]

def test_kept_fully_covered_dropped():
    out = s.merge_charge_groups([g(6,30,7,0)], [g(6,0,7,59,"ForceCharge")])
    assert spans(out) == [("ForceCharge","06:00","07:59")]

def test_find_overlaps():
    assert s.find_overlaps([g(0,0,23,59), g(6,0,7,59,"ForceCharge")]) == [(0,1)]
    assert s.find_overlaps([g(0,0,5,59), g(6,0,7,59)]) == []
    assert s.find_overlaps([g(0,0,6,0), g(6,0,7,59)]) == [(0,1)]
    assert s.find_overlaps([g(0,0,23,59), g(6,0,7,59, enable=0)]) == []

def test_moving_window_leaves_no_gap():
    first = s.merge_charge_groups([g(0,0,23,59)], [g(6,0,7,59,"ForceCharge")])
    kept = [x for x in first if x["workMode"] != "ForceCharge"]
    old = [(s.start_min(x), s.end_min(x)) for x in first if x["workMode"] == "ForceCharge"]
    second = s.merge_charge_groups(kept, [g(7,0,7,59,"ForceCharge")], old)
    assert spans(second) == [("SelfUse","00:00","06:59"),("ForceCharge","07:00","07:59"),("SelfUse","08:00","23:59")]

def test_rejoin_only_same_settings():
    out = s.rejoin([g(0,0,5,59), g(8,0,23,59,"Feedin")], [(360, 479)])
    assert spans(out) == [("SelfUse","00:00","05:59"),("Feedin","08:00","23:59")]
