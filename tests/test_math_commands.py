"""常用数学命令的原文往返、原生编译及受控支持范围；正文均为原创。"""

import json
import re

import pytest
from test_portrait_math import compile_tex

from note2lecture.diagnostics import NoteError
from note2lecture.document import read_document
from note2lecture.exporter import prepare_ast, restore_display_math
from note2lecture.math_commands import MARKDOWN_MATH_COMMANDS, MARKDOWN_MATH_GROUPS
from note2lecture.tools import pandoc

# 每个新增命令至少在一个有实际参数的公式中经原生 TeX 编译验证。
COMMAND_CASES = {
    "relations": [
        r"a\not=b,\quad x\stackrel{\mathrm{def}}=y",
        r"a\nleq b\ngeq c\nless d\ngtr e\asymp f\cong g",
        r"a\prec b\preceq c\succ d\succeq e",
        r"a\parallel b\nparallel c\nmid d\models e\vdash f\dashv g\bowtie h",
        r"A\subsetneq B\supsetneq C",
    ],
    "operators": [
        r"\sinh x+\cosh x+\tanh x+\coth x+\sec x+\csc x",
        r"\Pr(A),\quad\gcd(m,n),\quad\deg p,\quad\hom(A,B),\quad\ker T,\quad\lg x",
        r"\limsup_{n\to\infty}a_n,\quad\liminf_{n\to\infty}b_n",
    ],
    "sets": [
        r"\bigcap_i A_i,\quad\bigvee_i p_i,\quad\bigwedge_i q_i",
        r"\bigoplus_i V_i,\quad\bigotimes_i W_i,\quad\biguplus_i B_i,\quad\coprod_i C_i",
        r"A\sqcup B\sqcap C\uplus D,\quad\complement A",
    ],
    "arrows": [
        r"A\longleftarrow B\longleftrightarrow C\Longleftarrow D",
        r"A\hookrightarrow B\hookleftarrow C\leftrightarrow D",
        r"a\nearrow b\searrow c\nwarrow d\swarrow e",
        r"a\updownarrow b\Uparrow c\Downarrow d\Updownarrow e\rightleftharpoons f",
    ],
    "fonts": [
        r"\mathscr{F}+\mathfrak{g}+\mathnormal{x}",
        r"\mathop{T}_{n=1}x\mathrel{=}y\mathbin{+}z",
        r"\mathopen{(}\mathord{x}\mathpunct{,}\mathinner{y}\mathclose{)}",
        r"\textnormal{normal}+\textbf{bold}+\textit{italic}+\textsf{sans}+\texttt{mono}",
    ],
    "accents": [
        r"\acute{x}+\grave{x}+\breve{x}+\check{x}+\mathring{x}",
        r"\overrightarrow{AB}+\overleftarrow{CD}+\overleftrightarrow{EF}",
        r"\underleftarrow{GH}+\underrightarrow{IJ}",
    ],
    "fractions": [r"\tbinom{n}{k}"],
    "delimiters": [
        r"\lfloor x\rfloor+\lceil y\rceil",
        r"\biggl(x\biggr)+\Biggl(y\Biggr)",
    ],
    "spacing": [r"a\thinspace b\medspace c\thickspace d\negthinspace e\enspace f"],
    "integrals": [r"\oint_C f\,dz,\quad\iiiint_\Omega g\,dV,\quad\idotsint h,\quad\oiiint_S u"],
    "more_relations": [
        r"a\leqslant b\geqslant c\lesssim d\gtrsim e\lessapprox f\gtrapprox g",
        r"a\doteq b\doteqdot c\triangleq d\eqsim e\approxeq f\lessgtr g\gtrless h\Doteq j",
        r"A\nsubseteq B\nsupseteq C",
        r"A\sqsubset B\sqsupset C\sqsubseteq D\sqsupseteq E",
    ],
    "more_symbols": [r"\hbar+\hslash+\imath+\jmath+\wp+\aleph+\beth+\gimel+\daleth+\eth+\varkappa"],
    "more_accents": [r"\dddot{x}+\ddddot{x}"],
    "proof_symbols": [r"x=y\quad\blacksquare"],
    "transform_arrows": [r"A\xleftarrow{R_1-R_2}B"],
}


def test_every_new_command_has_a_native_compile_example():
    covered = {
        match[1] for formulas in COMMAND_CASES.values() for formula in formulas
        for match in re.finditer(r"\\([A-Za-z]+)", formula)
    }
    added = MARKDOWN_MATH_COMMANDS - set(MARKDOWN_MATH_GROUPS["existing"].split())
    assert added <= covered


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("group", COMMAND_CASES)
def test_standard_commands_survive_backend_exactly(tmp_path, quarto, profile, group):
    formulas = COMMAND_CASES[group]
    path = tmp_path / "original.md"
    original = "# 原创数学命令\n\n" + "\n\n".join("$$" + x + "$$" for x in formulas)
    path.write_text(original, encoding="utf-8")
    doc = read_document(path, quarto, profile)
    assert [item["text"] for item in doc.math] == formulas
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc,
    )
    assert all(formula in tex for formula in formulas)
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("group", COMMAND_CASES)
def test_standard_commands_compile_with_existing_template(tmp_path, group):
    body = r"\begin{document}" + "\n".join(r"\[" + x + r"\]" for x in COMMAND_CASES[group])
    result, log = compile_tex(tmp_path, body + r"\end{document}")
    assert result.returncode == 0, log[-3000:]
    assert not re.search(r"Missing character|Overfull|Undefined control sequence", log)


@pytest.mark.parametrize("command", [
    r"\input{private}", r"\include{private}", r"\write18{command}",
    r"\csname input\endcsname", r"\def\mine{x}", r"\newcommand{\mine}{x}",
    r"\usepackage{extra}", r"\unknownmacro{x}", r"\require{extra}",
])
def test_non_math_and_unknown_commands_remain_rejected(tmp_path, quarto, command):
    path = tmp_path / "original.md"
    path.write_text("# 原创\n\n$$" + command + "$$", encoding="utf-8")
    with pytest.raises(NoteError) as error:
        read_document(path, quarto, "markdown")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"


@pytest.mark.parametrize("command", [r"\not=", r"\stackrel{x}=y", r"\Pr(A)"])
def test_strict_command_scope_is_unchanged(tmp_path, quarto, command):
    path = tmp_path / "original.md"
    path.write_text(
        "---\ntitle: 原创\nauthor: 原创示例\n---\n\n$$\n" + command + "\n$$", encoding="utf-8",
    )
    with pytest.raises(NoteError) as error:
        read_document(path, quarto, "strict")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"


def test_unknown_commands_are_collected_once_without_code_literals(tmp_path, quarto):
    path = tmp_path / "original.md"
    path.write_text(
        "# 原创\n\n代码 `\\onlycode`。\n\n$$\\missingone{x}$$\n\n"
        "$$\\missingtwo{y}+\\missingone{z}$$\n\n```text\n\\onlyfence\n```",
        encoding="utf-8",
    )
    with pytest.raises(NoteError) as error:
        read_document(path, quarto, "markdown")
    diagnostic = error.value.diagnostic
    assert diagnostic.message == r"不支持的数学命令：\missingone、\missingtwo"
    assert [x["command"] for x in diagnostic.related] == [r"\missingone", r"\missingtwo"]
    assert [x["line"] for x in diagnostic.related] == [5, 7]
    assert [x["approximate"] for x in diagnostic.related] == [True, False]


def test_heading_with_math_keeps_location_after_command_check(tmp_path, quarto):
    path = tmp_path / "original.md"
    path.write_text("# 原创\n\n## 第一节\n\n#### 跳级 $x$\n", encoding="utf-8")
    with pytest.raises(NoteError) as error:
        read_document(path, quarto, "markdown")
    diagnostic = error.value.diagnostic
    assert diagnostic.code == "INPUT_METADATA"
    assert (diagnostic.line, diagnostic.column, diagnostic.approximate) == (5, 1, False)
