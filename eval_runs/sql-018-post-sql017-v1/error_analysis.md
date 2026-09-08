# sql-018-post-sql017-v1 Error Analysis

Failed cases: 12/30
Compatible result mismatches: 5
Strict result mismatches: 5
Trace deviations: 12

## A01 - Schema Linking Error

- Bucket: aggregate
- Question: 全部有效订单的GMV是多少
- Error: result or structure mismatch
- Failure labels: Schema Linking Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: None

## A02 - Metric Recognition Error

- Bucket: aggregate
- Question: 全部有效订单的整体订单量是多少
- Error: result or structure mismatch
- Failure labels: Metric Recognition Error, Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## A04 - Schema Linking Error

- Bucket: aggregate
- Question: 支付明细一共有多少条记录
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## A05 - Schema Linking Error

- Bucket: aggregate
- Question: 订单商品明细一共有多少件
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## T01 - Schema Linking Error

- Bucket: time
- Question: 2018年5月GMV是多少
- Error: result or structure mismatch
- Failure labels: Schema Linking Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: None

## T04 - Schema Linking Error

- Bucket: time
- Question: 2018年第二季度的AOV是多少
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## T05 - Schema Linking Error

- Bucket: time
- Question: 列出2018年5月每日GMV，按日期排序
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Result Value Mismatch, Result Shape Mismatch
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: None

## J02 - SQL Generation Error

- Bucket: join
- Question: 按商品英文品类统计有效订单GMV
- Error: SQL uses a column outside SchemaLinkingPlan
- Failure labels: SQL Generation Error, Schema Linking Error, Grain Contract Error
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: 0.0

## N02 - SQL Generation Error

- Bucket: topn
- Question: 2018年5月GMV最高的5个商品品类是什么
- Error: function is not allowlisted: any_value
- Failure labels: SQL Generation Error, Schema Linking Error, Grain Contract Error
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: 0.0

## N03 - SQL Generation Error

- Bucket: topn
- Question: 有效订单GMV最高的5个卖家是谁
- Error: DWD GMV must sum order-item price and exclude canceled/unavailable orders
- Failure labels: SQL Generation Error, Schema Linking Error, Grain Contract Error
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: 0.0

## N05 - Schema Linking Error

- Bucket: topn
- Question: 支付明细记录数最多的3种付款方式是什么
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## C05 - Schema Linking Error

- Bucket: comparison
- Question: 对比2018年4月和5月已送达与已取消订单的数量
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Result Value Mismatch, Result Shape Mismatch
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: None
