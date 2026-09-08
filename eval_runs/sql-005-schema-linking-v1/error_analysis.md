# sql-005-schema-linking-v1 Error Analysis

Failed cases: 18/30

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

## A02 - Schema Linking Error

- Bucket: aggregate
- Question: 全部有效订单的整体订单量是多少
- Error: result or structure mismatch
- Execution match: False

## A04 - Schema Linking Error

- Bucket: aggregate
- Question: 支付明细一共有多少条记录
- Error: result or structure mismatch
- Execution match: True

## A05 - Metric Recognition Error

- Bucket: aggregate
- Question: 订单商品明细一共有多少件
- Error: result or structure mismatch
- Execution match: True

## T02 - Schema Linking Error

- Bucket: time
- Question: 按月统计2018年的GMV趋势
- Error: result or structure mismatch
- Execution match: True

## T03 - Schema Linking Error

- Bucket: time
- Question: 2018年5月整体订单数是多少
- Error: result or structure mismatch
- Execution match: False

## T04 - Schema Linking Error

- Bucket: time
- Question: 2018年第二季度的AOV是多少
- Error: result or structure mismatch
- Execution match: True

## T05 - Schema Linking Error

- Bucket: time
- Question: 列出2018年5月每日GMV，按日期排序
- Error: result or structure mismatch
- Execution match: False

## J02 - SQL Generation Error

- Bucket: join
- Question: 按商品英文品类统计有效订单GMV
- Error: result or structure mismatch
- Execution match: False

## J03 - Metric Recognition Error

- Bucket: join
- Question: 按付款方式统计有效订单的支付明细记录数
- Error: result or structure mismatch
- Execution match: False

## J05 - Schema Linking Error

- Bucket: join
- Question: 按客户所在巴西州统计评价记录数
- Error: result or structure mismatch
- Execution match: True

## N04 - Schema Linking Error

- Bucket: topn
- Question: 2018年5月商品项数最多的5个品类是什么
- Error: result or structure mismatch
- Execution match: False

## N05 - Schema Linking Error

- Bucket: topn
- Question: 支付明细记录数最多的3种付款方式是什么
- Error: result or structure mismatch
- Execution match: True

## C01 - SQL Generation Error

- Bucket: comparison
- Question: 对比2018年4月和5月的GMV
- Error: function is not allowlisted: left
- Execution match: False

## C04 - Schema Linking Error

- Bucket: comparison
- Question: 对比2018年4月和5月的AOV
- Error: result or structure mismatch
- Execution match: False

## C05 - Metric Recognition Error

- Bucket: comparison
- Question: 对比2018年4月和5月已送达与已取消订单的数量
- Error: result or structure mismatch
- Execution match: False
