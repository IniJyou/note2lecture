"""普通 Markdown 的常见数学命令；仅使用现有模板可提供的标准命令。"""

# 按用途集中维护，避免在逐个公式的校验循环里不断临时增加特例。
# strict 的 N0 白名单仍留在 document.py，不随此扩展改变。
MARKDOWN_MATH_GROUPS = {
    "existing": """
longrightarrow Longrightarrow mid odot dim arcsin arccos arctan cot boxed
bigl bigr Bigl Bigr uparrow downarrow therefore Longleftrightarrow square tag
iiint oiint lt gt xrightarrow dagger checkmark arg bigcup
""",
    "relations": """
not stackrel nleq ngeq nless ngtr asymp cong prec preceq succ succeq
parallel nparallel nmid models vdash dashv bowtie subsetneq supsetneq
""",
    "operators": "sinh cosh tanh coth sec csc Pr gcd deg hom ker lg limsup liminf",
    "sets": """
bigcap bigvee bigwedge bigoplus bigotimes biguplus coprod sqcup sqcap uplus complement
""",
    "arrows": """
longleftarrow longleftrightarrow Longleftarrow hookrightarrow hookleftarrow
leftrightarrow nearrow searrow nwarrow swarrow updownarrow Uparrow Downarrow
Updownarrow rightleftharpoons
""",
    "fonts": """
mathscr mathfrak mathnormal mathop mathrel mathbin mathord mathopen mathclose
mathpunct mathinner textnormal textbf textit textsf texttt
""",
    "accents": """
acute grave breve check mathring overrightarrow overleftarrow overleftrightarrow
underleftarrow underrightarrow
""",
    "fractions": "tbinom",
    "delimiters": "lfloor rfloor lceil rceil biggl biggr Biggl Biggr",
    "spacing": "thinspace medspace thickspace negthinspace enspace",
    "integrals": "oint iiiint idotsint oiiint",
    "more_relations": """
leqslant geqslant lesssim gtrsim lessapprox gtrapprox doteq doteqdot triangleq
eqsim approxeq lessgtr gtrless nsubseteq nsupseteq Doteq
sqsubset sqsupset sqsubseteq sqsupseteq
""",
    "more_symbols": "hbar hslash imath jmath wp aleph beth gimel daleth eth varkappa",
    "more_accents": "dddot ddddot",
    "proof_symbols": "blacksquare",
    "transform_arrows": "xleftarrow",
}
MARKDOWN_MATH_COMMANDS = frozenset(
    command for group in MARKDOWN_MATH_GROUPS.values() for command in group.split()
)
