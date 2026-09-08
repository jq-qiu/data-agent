# sql-008-metric-calendar-v1 Error Analysis

Failed cases: 14/30

## S03 - SQL Generation Error

- Bucket: simple
- Question: Olist订单有哪些订单状态
- Error: result or structure mismatch
- Execution match: False

## S04 - SQL Generation Error

- Bucket: simple
- Question: 支付记录中有哪些付款方式
- Error: result or structure mismatch
- Execution match: False

## A01 - Schema Linking Error

- Bucket: aggregate
- Question: 全部有效订单的GMV是多少
- Error: result or structure mismatch
- Execution match: True

## A04 - Schema Linking Error

- Bucket: aggregate
- Question: 支付明细一共有多少条记录
- Error: result or structure mismatch
- Execution match: True

## A05 - Metric Recognition Error

- Bucket: aggregate
- Question: 订单商品明细一共有多少件
- Error: result or structure mismatch
- Execution match: False

## T01 - Schema Linking Error

- Bucket: time
- Question: 2018年5月GMV是多少
- Error: result or structure mismatch
- Execution match: True

## T04 - Schema Linking Error

- Bucket: time
- Question: 2018年第二季度的AOV是多少
- Error: result or structure mismatch
- Execution match: True

## J02 - SQL Generation Error

- Bucket: join
- Question: 按商品英文品类统计有效订单GMV
- Error: result or structure mismatch
- Execution match: False

## J03 - Schema Linking Error

- Bucket: join
- Question: 按付款方式统计有效订单的支付明细记录数
- Error: result or structure mismatch
- Execution match: False

## N02 - Schema Linking Error

- Bucket: topn
- Question: 2018年5月GMV最高的5个商品品类是什么
- Error: result or structure mismatch
- Execution match: True

## N05 - Schema Linking Error

- Bucket: topn
- Question: 支付明细记录数最多的3种付款方式是什么
- Error: result or structure mismatch
- Execution match: True

## C02 - SQL Generation Error

- Bucket: comparison
- Question: 对比2018年4月和5月的整体订单数
- Error: result or structure mismatch
- Execution match: False

## C04 - SQL Generation Error

- Bucket: comparison
- Question: 对比2018年4月和5月的AOV
- Error: result or structure mismatch
- Execution match: False

## C05 - Metric Recognition Error

- Bucket: comparison
- Question: 对比2018年4月和5月已送达与已取消订单的数量
- Error: result or structure mismatch
- Execution match: False
