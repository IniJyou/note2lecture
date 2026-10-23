-- 代码只作为文件内容排版：即使含 \end{Verbatim}，也不能逃出代码环境。
function CodeBlock(el)
  local filename = el.attributes["n2l-code"]
  if not filename or not filename:match("^code/%x+%.txt$") then
    error("Note2Lecture: missing controlled code resource")
  end
  return pandoc.RawBlock("latex",
    "\\VerbatimInput[fontsize=\\footnotesize,baselinestretch=1.1," ..
    "breaklines=true,breakanywhere=true," ..
    "breaksymbolleft={},frame=single,rulecolor=\\color{gray!40}," ..
    "framesep=2mm]{" .. filename .. "}")
end
