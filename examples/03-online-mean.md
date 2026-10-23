---
title: "逐项更新平均值：先保留计数"
author: "Note2Lecture 示例"
date: "2026-10-23"
lang: "zh-CN"
---

# 从总和到更新式 {#sec-update}

设 $x_1,\ldots,x_n\in\mathbb{R}$，$n\geq 2$，$m_{n-1}$ 是前 $n-1$ 个数的平均值。把新数据加入后，可以不保存完整历史序列，只保存计数与平均值。

$$
\begin{aligned}
m_n
&=\frac{1}{n}\left(\sum_{i=1}^{n-1}x_i+x_n\right)\\
&=\frac{(n-1)m_{n-1}+x_n}{n}\\
&=m_{n-1}+\frac{x_n-m_{n-1}}{n}.
\end{aligned}
$$ {#eq-online-mean}

第一项单独初始化为 $m_1=x_1$。上式是实数运算下的等式；浮点实现的舍入误差需要另行分析。

## 固定序列的手算 {#sec-trace}

| 步骤 $n$ | 新值 $x_n$ | 先前均值 | 差值 | 更新后均值 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 无 | 无 | 2 |
| 2 | 4 | 2 | 2 | 3 |
| 3 | 8 | 3 | 5 | $14/3$ |
| 4 | 10 | $14/3$ | $16/3$ | 6 |

: 逐项处理序列 2、4、8、10 {#tbl-mean-trace}

@tbl-mean-trace 的最后一行也可以用总和 $24$ 除以个数 $4$ 验证。第三行保留分数，避免中间小数舍入干扰手算。

# 合并两批记录 {#sec-merge}

![四个数分成两批，每批保留自己的计数与均值](<assets/批次 示意.jpg>){#fig-batches}

@fig-batches 中，A 批为 $2,4$，均值为 $3$；B 批为 $8,10$，均值为 $9$。一般地，设两批非空，计数为正整数 $n_A,n_B$，均值分别为 $m_A,m_B$，则合并均值为

$$
m=\frac{n_A m_A+n_B m_B}{n_A+n_B}.
$$ {#eq-merge-mean}

本例两批一样大，因此 $m=(3+9)/2=6$。当批大小不同时，直接平均两个均值通常会出错；@eq-merge-mean 中的计数不能省略。

## 实现时保留什么 {#sec-state}

下面的代码展示状态更新。最后的字符串故意写成较长的一行，用于观察讲义的视觉折行；可编辑源文件中的代码内容应保留。

```python
def update_mean(count, mean, value):
    if count < 0:
        raise ValueError("count must be nonnegative")
    new_count = count + 1
    if count == 0:
        return new_count, value
    new_mean = mean + (value - mean) / new_count
    return new_count, new_mean

count, mean = 0, 0.0
for value in [2, 4, 8, 10]:
    count, mean = update_mean(count, mean, value)

message = "Keep the sample count with the running mean; merging batches with different counts requires weighting each batch mean by its own count."
```

检视结果时，先核对计数是否为 $4$、平均值是否为 $6$，再核对 @eq-online-mean 与 @eq-merge-mean 的符号。只看最终一个数，不能排除过程中丢失了一条记录。

# 阅读检查 {#sec-review}

公式、表格和图片分别承担不同的说明任务：公式说明更新关系，表格保存中间值，图片展示分批方式。它们可以排在相邻页面，但图题、表题和引用必须对应，不能把表格里“无”的初始化状态替换成计算所得的零。

排版时允许代码在页面上折行，也允许章节自然换页。不得用删去代码尾部、裁切图片、缩小整页或改变公式含义来让内容塞进一页。
