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
    if #item > 1 and (first.t == "Para" or first.t == "Plain") then
      local title, only_title = false, true
      for _, inline in ipairs(first.content) do
        if inline.t == "Strong" then
          title = true
        elseif inline.t == "Str" and (inline.text == ":" or inline.text == "：") then
          -- 题头的冒号也可能写在粗体外面，仍须与后面的公式连排。
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

local keep_next = "\\nopagebreak[4]"
local function is_display(inline)
  return (inline.t == "RawInline" or inline.t == "RawBlock")
    and (inline.format == "latex" or inline.format == "tex")
    and inline.text:match("^\\NtwoLMathDisplay{") ~= nil
end

local function short_text(inlines)
  local text = pandoc.utils.stringify(pandoc.Plain(inlines))
  -- 长摘要只是内部公式保护标记，计算可见长度时相当于一个数学符号。
  text = text:gsub("\\NtwoLMathToken%b{}", "x")
  return text:match("%S") ~= nil and (utf8.len(text) or #text) <= 80
end

local function keep_after(inline)
  if inline.text:sub(-#keep_next) ~= keep_next then
    -- 显示公式自身的断页点先于末尾的 nopagebreak；须在公式开始前局部提高罚值。
    inline.text = "\\begingroup\\postdisplaypenalty=10000\n" .. inline.text
      .. "\n\\endgroup" .. keep_next
  end
  return inline
end

-- 同段公式后的短结语保持连排，避免短结语单独占据下一页。
function Para(para)
  for index = #para.content, 1, -1 do
    if is_display(para.content[index]) then
      local tail = {}
      for next_index = index + 1, #para.content do
        tail[#tail + 1] = para.content[next_index]
      end
      if index < #para.content and short_text(tail) then
        local content = para.content
        content[index] = keep_after(content[index])
        para.content = content
      end
      break
    end
  end
  return para
end

-- 容器末尾的独立公式与短结语也连排；源位置注释不属于可见内容。
function Blocks(blocks)
  local visible = {}
  for index, block in ipairs(blocks) do
    if not (block.t == "RawBlock" and block.format == "latex"
        and block.text:match("^%% N2L_SOURCE")) then
      visible[#visible + 1] = index
    end
  end
  if #visible < 2 then return blocks end
  local previous, last = blocks[visible[#visible - 1]], blocks[visible[#visible]]
  if is_display(previous) and last.t == "Para" and short_text(last.content) then
    blocks[visible[#visible - 1]] = keep_after(previous)
  elseif previous.t == "Para" and last.t == "Para" and #previous.content == 1
      and is_display(previous.content[1]) and short_text(last.content) then
    local content = previous.content
    content[1] = keep_after(content[1])
    previous.content = content
    blocks[visible[#visible - 1]] = previous
  end
  return blocks
end
