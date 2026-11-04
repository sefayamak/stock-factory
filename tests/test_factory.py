from io import BytesIO
from PIL import Image
from src.factory import validate_image, choose_jobs, make_prompt, run

def test_small_short_edge_rejected():
    b=BytesIO();Image.new('RGB',(2752,1536),'blue').save(b,format='JPEG')
    ok,reason,_=validate_image(b.getvalue())
    assert not ok and reason=='short_edge_below_2048'

def test_four_k_pass():
    b=BytesIO();Image.new('RGB',(4096,3072),'blue').save(b,format='JPEG')
    assert validate_image(b.getvalue())[0]

def test_deterministic_jobs():
    assert choose_jobs('2026-11-04',3)==choose_jobs('2026-11-04',3)

def test_dry_run_no_jpegs(tmp_path):
    run(tmp_path,'2026-11-04',3,True)
    assert len(list(tmp_path.glob('*.jpg')))==0
    assert (tmp_path/'submission.csv').exists()
