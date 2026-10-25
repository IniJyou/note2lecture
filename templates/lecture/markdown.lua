-- 行内断点是受控 LaTeX，不能让宏的文本长度影响表格的列宽估计。
-- 基础表格等宽分配；不猜测内容重要性，不缩小表格正文。
function Table(tbl)
  local width = 1 / #tbl.colspecs
  for _, column in ipairs(tbl.colspecs) do
    column[2] = width
  end
  return tbl
end
