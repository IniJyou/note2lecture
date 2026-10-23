---
title: "从三个数理解算术平均"
author: "Note2Lecture 示例"
date: "2026-10-23"
lang: "zh-CN"
---

# 平均值的含义 {#sec-mean}

把三个相同容量的杯子想成三个数的位置。我们只关心每个位置上的数，不涉及测量误差。**算术平均**回答的是：如果总量不变，每个位置分到多少？[^scope]

设 $n$ 为正整数，$x_1,\ldots,x_n\in\mathbb{R}$。它们的算术平均为

$$
\bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i.
$$ {#eq-mean}

对于 $2,4,9$，总和为 $15$，所以 $\bar{x}=5$。不要把*平均值*和“序列中间位置的值”混为一谈；这里的中位数是 $4$。

## 手算顺序 {#sec-steps}

1. 数清数据个数，本例为 $n=3$。
2. 计算总和 $2+4+9=15$。
3. 用总和除以个数，得到 $15/3=5$。

![先求总和，再除以数据个数](assets/mean-flow.png){#fig-mean-flow}

@fig-mean-flow 展示了 @eq-mean 的计算顺序；它不要求输入已经排序。

### 简单复核 {#sec-check}

本例的 $5$ 落在最小值 $2$ 与最大值 $9$ 之间。这是一个快速复核线索，但仅凭这个条件还不能确定平均值算对了。

# 写成短程序 {#sec-code}

下面的 Python 代码只是讲义中的内容。`values` 保存原始次序，空输入应当明确报错。

```python
def arithmetic_mean(values):
    # 空序列没有这里定义的算术平均。
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / len(values)

values = [2, 4, 9]
result = arithmetic_mean(values)  # 手算期望值：5.0
```

复核时注意两点：

- 分母是数据个数，不是最大数。
- 数据可以重复，也可以包含负数。
    - 重复出现的数按实际出现次数计入。
    - 负数保留原来的符号。

计算完成后，可以回到 @sec-check 做一次快速复核。

> 一个极端值会拉动算术平均。解释平均值之前，应先说明数据代表什么。

格式记号可对照 [Markdown 语法说明](https://daringfireball.net/projects/markdown/syntax) 阅读；导出时只保留链接，不访问该网页。

[^scope]: 本例仅讨论有限个实数的算术平均，不把它当作概率分布期望的一般定义。
