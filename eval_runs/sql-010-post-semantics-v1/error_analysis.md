# sql-010-post-semantics-v1 Error Analysis

Failed cases: 15/30
Compatible result mismatches: 4
Strict result mismatches: 4
Trace deviations: 14

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

## T03 - SQL Generation Error

- Bucket: time
- Question: 2018年5月整体订单数是多少
- Error: SQL omits required Metric Registry columns
- Failure labels: SQL Generation Error, Schema Linking Error, Grain Contract Error
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: 0.0

## T04 - Schema Linking Error

- Bucket: time
- Question: 2018年第二季度的AOV是多少
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## J02 - SQL Generation Error

- Bucket: join
- Question: 按商品英文品类统计有效订单GMV
- Error: result or structure mismatch
- Failure labels: Result Value Mismatch, Result Shape Mismatch
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: True
- Grain contract: 1.0

## N02 - Schema Linking Error

- Bucket: topn
- Question: 2018年5月GMV最高的5个商品品类是什么
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## N03 - Schema Linking Error

- Bucket: topn
- Question: 有效订单GMV最高的5个卖家是谁
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: 0.0

## N04 - None

- Bucket: topn
- Question: 2018年5月商品项数最多的5个品类是什么
- Error: result or structure mismatch
- Failure labels: Schema Linking Error, Grain Contract Error
- Compatible execution match: True
- Strict execution match: 1.0
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

## C01 - None

- Bucket: comparison
- Question: 对比2018年4月和5月的GMV
- Error: result or structure mismatch
- Failure labels: Schema Linking Error
- Compatible execution match: True
- Strict execution match: 1.0
- Trace conformance: False
- Grain contract: None

## C02 - SQL Generation Error

- Bucket: comparison
- Question: 对比2018年4月和5月的整体订单数
- Error: dim_date.year requires an integer literal
- Failure labels: SQL Generation Error, Schema Linking Error, Grain Contract Error
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: 0.0

## C05 - SQL Generation Error

- Bucket: comparison
- Question: 对比2018年4月和5月已送达与已取消订单的数量
- Error: SQL GROUP BY differs from SchemaLinkingPlan
- Failure labels: SQL Generation Error, Schema Linking Error
- Compatible execution match: False
- Strict execution match: 0.0
- Trace conformance: False
- Grain contract: None
