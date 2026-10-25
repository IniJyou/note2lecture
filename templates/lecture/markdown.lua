-- 行内断点是受控 LaTeX，不能让宏的文本长度影响表格的列宽估计。
-- 基础表格等宽分配；不猜测内容重要性，不缩小表格正文。
function Table(tbl)
  local width = 1 / #tbl.colspecs
  for _, column in ipairs(tbl.colspecs) do
    column[2] = width
  end
  return tbl
end

-- 列表内粗体独占的题头与下一段相连，后接大公式时也不能独留在上一页。
local function keep_list_titles(list)
  for _, item in ipairs(list.content) do
    local first = item[1]
    if #item > 1 and first.t == "Para" then
      local title, only_title = false, true
      for _, inline in ipairs(first.content) do
        if inline.t == "Strong" then
          title = true
        elseif inline.t ~= "Space" and inline.t ~= "SoftBreak" then
          only_title = false
        end
      end
      if title and only_title then
        first.content:insert(pandoc.RawInline("latex", "\\nopagebreak[4]"))
      end
    end
  end
  return list
end

BulletList = keep_list_titles
OrderedList = keep_list_titles
