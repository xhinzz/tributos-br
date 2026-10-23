"""O exemplo de abertura do README roda e imprime exatamente o que o README mostra."""

import contextlib
import io
import re
from pathlib import Path

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")


def test_exemplo_do_readme():
    codigo, saida = re.search(r"```python\n(.*?)```\n\n```\n(.*?)```", README, re.S).groups()
    impresso = io.StringIO()
    with contextlib.redirect_stdout(impresso):
        exec(codigo, {})
    assert impresso.getvalue() == saida
