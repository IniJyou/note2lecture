---
title: "一维正交投影为什么最近"
author: "Note2Lecture 示例"
date: "2026-10-23"
lang: "zh-CN"
---

# 从一个方向开始 {#sec-direction}

给定列向量 $x,u\in\mathbb{R}^{d\times 1}$，其中 $d$ 为正整数且 $u\ne 0$。内积 $u^\top x$ 和 $u^\top u$ 都是标量。我们要在直线 $\{au:a\in\mathbb{R}\}$ 上寻找离 $x$ 最近的点，结论见 @thm-nearest。

::: {#def-projection}

## 一维正交投影

向量 $x$ 在方向 $u$ 上的投影定义为

$$
p=\frac{u^\top x}{u^\top u}u.
$$ {#eq-projection}

这里 $p\in\mathbb{R}^{d\times 1}$，分母严格大于零。
:::

::: {#lem-orthogonal}

## 残差与方向正交

按 @def-projection 取 $p$，则 $u^\top(x-p)=0$。
:::

::: {.proof}
代入 @eq-projection，得到

$$
u^\top(x-p)
=u^\top x-\frac{u^\top x}{u^\top u}u^\top u
=0.
$$

因此残差 $x-p$ 与 $u$ 正交。
:::

# 最近点性质 {#sec-nearest}

::: {#thm-nearest}

## 直线上的唯一最近点

若 $u\ne 0$，则对任意实数 $a$，都有 $\lVert x-au\rVert_2^2\geq\lVert x-p\rVert_2^2$；等号当且仅当 $a=(u^\top x)/(u^\top u)$。
:::

::: {.proof}
记 $a_*=(u^\top x)/(u^\top u)$。由 @lem-orthogonal，交叉项为零，所以

$$
\begin{aligned}
\lVert x-au\rVert_2^2
&=\lVert (x-p)+(a_*-a)u\rVert_2^2\\
&=\lVert x-p\rVert_2^2+(a_*-a)^2\lVert u\rVert_2^2.
\end{aligned}
$$ {#eq-distance}

第二项非负，并且因 $u\ne 0$，仅在 $a=a_*$ 时为零。这同时给出最小性和唯一性。
:::

::: {#exm-two-dimensional}

## 二维数值核对

取 $x=(2,3)^\top$、$u=(1,0)^\top$。此时 $p=(2,0)^\top$，最小平方距离为 $9$。若改取 $a=1$，平方距离为 $10$，与 @eq-distance 一致。
:::

@exm-two-dimensional 中的坐标仅用于手算。若允许 $u=0$，@eq-projection 的分母为零，因此不能去掉 @thm-nearest 的非零条件。
