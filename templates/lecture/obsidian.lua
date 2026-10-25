-- 只处理程序生成的提示框，不执行正文代码，也不把提示框分类为数学环境。
function Div(div)
  if div.classes:includes("n2l-callout") then
    local blocks = pandoc.List({pandoc.RawBlock("latex", "\\begin{NtwoLCallout}")})
    blocks:extend(div.content)
    blocks:insert(pandoc.RawBlock("latex", "\\end{NtwoLCallout}"))
    return blocks
  end
end
