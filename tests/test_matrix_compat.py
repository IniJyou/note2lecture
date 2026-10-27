"""矩阵变换链、证明方块、数学书名与公式空行的原创回归。"""

import json
import re

import pytest
from test_portrait_math import compile_tex

from note2lecture.diagnostics import NoteError
from note2lecture.document import read_document
from note2lecture.exporter import prepare_ast, restore_display_math
from note2lecture.tools import pandoc, run


def read(tmp_path, quarto, text, profile="markdown"):
    path = tmp_path / "original.md"
    path.write_text(text, encoding="utf-8")
    return read_document(path, quarto, profile)


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
def test_math_title_preserves_source_math_and_controlled_metadata(tmp_path, quarto, profile):
    text = "# $ \\lambda $空间与变换\n\n## 第一节\n\n正文 $u$。\n"
    doc = read(tmp_path, quarto, text, profile)
    assert [m["text"] for m in doc.math] == [r" \lambda ", "u"]
    assert doc.metadata["title"] == r"$ \lambda $空间与变换"
    assert r"\( \lambda \)" in doc.title_tex
    assert r"\textbackslash{}lambda" in doc.title_tex
    ast = prepare_ast(doc, tmp_path)
    tex = r"\title{" + doc.title_token + "}\n" + pandoc(quarto, json.dumps(ast), "json", "latex")
    restored = restore_display_math(tex, doc)
    assert doc.title_token not in restored and "NtwoLMathToken" not in restored
    assert r"\lambda " in restored and r"\(u\)" in restored
    assert doc.path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("title", [
    r"$\input{private}$", r"\input{private}", r"$$x$$", r"<script>text</script>",
])
def test_math_title_rejects_commands_and_unsupported_content(tmp_path, quarto, title):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# " + title + "\n\n正文。")
    assert error.value.diagnostic.code in {"INPUT_METADATA", "UNSUPPORTED_SYNTAX"}
    assert error.value.diagnostic.line == 1


def test_title_unknown_command_position_is_rebased_to_original_input(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "\n\n# 原创 $\\missing{x}$\n\n正文。")
    d = error.value.diagnostic
    assert (d.line, d.column) == (3, 7)
    assert (d.related[0]["line"], d.related[0]["column"]) == (3, 7)


def test_title_math_compiles_and_pdf_metadata_has_no_internal_token(tmp_path, quarto):
    doc = read(tmp_path, quarto, "# $\\lambda$空间\n\n正文。")
    tex = restore_display_math(r"\title{" + doc.title_token + "}", doc)
    body = (r"\usepackage{hyperref}" + tex + r"\hypersetup{pdftitle={" + doc.title_tex + "}}"
            r"\begin{document}\maketitle Original body.\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]
    assert not re.search(
        r"Missing character|Overfull|Token not allowed|Undefined control sequence", log,
    )
    info = run(["pdfinfo", tmp_path / "test.pdf"])
    assert info.returncode == 0 and "NtwoLTitle" not in info.stdout
    assert "lambda" in info.stdout


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("container", ["", "list", "quote"])
def test_formula_blank_lines_preserve_raw_math_and_source(tmp_path, quarto, profile, container):
    formula = "A=\\begin{pmatrix}\n1 & 2 \\\\\n\n3 & 4\n\\end{pmatrix}"
    body = "$$\n" + formula + "\n$$"
    if container == "list":
        body = "1. 原创矩阵\n\n   " + body.replace("\n", "\n   ")
    elif container == "quote":
        body = "> " + body.replace("\n", "\n> ")
    text = "# 原创\n\n" + body + "\n"
    doc = read(tmp_path, quarto, text, profile)
    assert len(doc.math_blank_lines) == 1
    assert [m["text"] for m in doc.math] == ["\n" + formula + "\n"]
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc,
    )
    assert formula in tex and "NtwoLBlank" not in tex
    assert doc.path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("formula", [
    "A=\\begin{pmatrix}1&2\\\\\n\n3&4\\end{pmatrix}",
    "x=\\frac\n\n{u}{v}", "x=\\frac{u\n\n+v}{w}",
])
def test_blank_math_native_normalization_preserves_parameters(tmp_path, formula):
    body = (r"\begin{document}\NtwoLMathDisplay{" + "a" * 64 + "}{" + formula + r"}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]
    assert not re.search(r"Missing character|Overfull|Undefined control sequence", log)


def test_blank_math_with_tag_stays_on_native_numbering_path(tmp_path, quarto):
    formula = "x=\\frac{u}{v}\n\n+1 \\tag{A}"
    doc = read(tmp_path, quarto, "# 原创\n\n$$\n" + formula + "\n$$")
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc,
    )
    assert r"\NtwoLMathWhitespace{" in tex and formula in tex
    result, log = compile_tex(tmp_path, r"\begin{document}" + tex + r"\end{document}")
    assert result.returncode == 0, log[-2500:]


def test_matrix_transform_arrows_wrap_with_labels_and_columns_intact(tmp_path):
    matrix = (r"\left(\begin{array}{cc|c}a_{k-1}&b_{k-1}&c_{k-1}"
              r"\\d_{k-1}&e_{k-1}&f_{k-1}\end{array}\right)")
    formula = matrix + r"\xrightarrow{R_1-R_2}" + matrix + r"\xrightarrow{R_2/3}" + matrix
    body = (r"\begin{document}\begin{minipage}{100mm}\NtwoLMathDisplay{"
            + "b" * 64 + "}{" + formula + r"}\end{minipage}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]
    assert "N2LWRAPPED:" in log
    assert not re.search(r"Missing character|Overfull|Undefined control sequence", log)


def test_arrow_label_groups_are_not_split_at_relations_or_minus(tmp_path):
    original = r"a\xrightarrow{u=v-w}b\xleftarrow{p=q-r}c"
    expected = r"a\xrightarrow{u=v-w}b\NtwoLWrapBreak\xleftarrow{p=q-r}c"
    body = (r"\begin{document}\ExplSyntaxOn\__ntwol_plan:n{" + original + "}"
            r"\tl_set:Nn\l_tmpa_tl{" + expected + "}"
            r"\tl_if_eq:NNF\l_tmpa_tl\l__ntwol_wrapped_tl{\errmessage{BADARROWBOUNDARY}}"
            r"\bool_if:NF\l__ntwol_safe_bool{\errmessage{UNSAFEARROW}}"
            r"\ExplSyntaxOff\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]


def test_whitespace_normalization_changes_only_par_tokens_inside_groups(tmp_path):
    body = (r"\begin{document}\ExplSyntaxOn"
            r"\__ntwol_clean:n{x=\frac{u\par+v}{w}+\sqrt{a\par-b}}"
            r"\tl_set:Nn\l_tmpa_tl{x=\frac{u~+v}{w}+\sqrt{a~-b}}"
            r"\tl_if_eq:NNF\l_tmpa_tl\l__ntwol_clean_math_tl{\errmessage{BADWHITESPACE}}"
            r"\ExplSyntaxOff\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]


def test_stackrel_relation_breaks_keep_both_annotation_arguments(tmp_path):
    formula = r"a\stackrel{u=v-w}{\simeq}b\stackrel{p=q-r}{\simeq}c"
    expected = r"a\stackrel{u=v-w}{\simeq}b\NtwoLWrapBreak\stackrel{p=q-r}{\simeq}c"
    body = (r"\begin{document}\ExplSyntaxOn\__ntwol_plan:n{" + formula + "}"
            r"\tl_set:Nn\l_tmpa_tl{" + expected + "}"
            r"\tl_if_eq:NNF\l_tmpa_tl\l__ntwol_wrapped_tl{\errmessage{BADANNOTATION}}"
            r"\bool_if:NF\l__ntwol_safe_bool{\errmessage{UNSAFEANNOTATION}}"
            r"\ExplSyntaxOff\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]


def test_multiline_stackrel_label_remains_atomic_in_wrapped_matrix_chain(tmp_path):
    matrix = r"\begin{pmatrix}p_{k-1}&q_{k-1}\\r_{k-1}&s_{k-1}\end{pmatrix}"
    label = r"r_2-r_1\\c_2-c_1"
    formula = r"\stackrel{r_1/2}{\simeq}" + matrix + r"\stackrel{" + label + r"}{\simeq}" + matrix
    body = (r"\begin{document}\begin{minipage}{55mm}\NtwoLMathDisplay{"
            + "c" * 64 + "}{" + formula + r"}\end{minipage}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]
    assert "N2LWRAPPED:" in log
    assert not re.search(r"Missing character|Overfull|Undefined control sequence", log)
