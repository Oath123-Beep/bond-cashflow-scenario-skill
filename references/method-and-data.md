# 方法、输入口径与数据来源

## 资料来源

- 用户提供的《金融市场与金融机构》第十版 PPT：第三章和第十二章的债券现值、持有期收益及例题。
- 上海证券交易所债券披露入口：https://bond.sse.com.cn/disclosure/ 。研究中国债券应按代码和期次核对条款，发行人与证券适格性须核实。
- GK25DDH2 的发行公告、最终票息来源及定位见 [bond-case-gk25ddh2.md](bond-case-gk25ddh2.md)；发行对象为专业投资者中的机构投资者，不推断个人交易资格。
- 美国国债历史拍卖数据：https://www.treasurydirect.gov/auctions/auction-query/auction-query-help/ 。历史拍卖和发行资料不等同当前交易报价。
- 美国10年期国债固定期限收益率：https://fred.stlouisfed.org/series/DGS10 。只能作为美国市场背景，不能替代特定中国债券的估值或成交数据。
- QuantLib 介绍及固定收益接口：https://www.quantlib.org/ ，https://quantlib-python-docs.readthedocs.io/en/latest/instruments/fixedincome.html 。单券对标前统一所有日期、价格与计息口径。

## Price 模式

JSON 文件包含 valuation_date（ISO日期，用于记载不自动生成现金流）、face_amount、frequency_per_year、annual_nominal_yield、cashflows（列表，每项 period、amount_per_100）。收益率以小数表示，例如0.12为12%。period是以付息频率对应的非负整数期数；amount_per_100以每100面值的现金额计。计算提供现金流的每100面值理论现值，再乘 face_amount/100 输出总额；只有提供的现金流完整且与结算口径匹配，才可能解释为理论全价。它不计算应计利息或净价，不支持不规则日期、现金流不确定或自动零息曲线，price 时点、利率及现金流须由用户自行确认。期初现金流和期末现金流不得遗漏或重复。

## Ledger 模式

输入以同一币种计：as_of、analysis_through（分析截止日，含当日）、initial_cash、bonds、sales、requirements。initial_cash 必须是截至 as_of 当日合同现金流已实际到账并计入、但输入中 as_of 当日卖出所得和支出尚未处理的余额；face_held 是处理输入中 as_of 当日出售之前的面值。程序不再将 as_of 当日或此前的合同现金流重复入账。如果当日合同现金流尚未到账、已发生的出售和支出是否计入无法确认，不能直接使用此口径计算。用户须提供观察期内完整现金流及准确日期，程序不自动从债券条款生成、补全或核验付息日。每只债券指定 id、face_held、cashflows；每条 cashflow 为 date、amount_per_100、kind（coupon 或 principal）。必须且只能提供一条每100面值归还100的到期本金现金流，且本金支付日必须晚于 as_of；缺失、分期还本或无法确定到期日的债券当前不支持。本金可在分析截止日之后，仅用于界定本金支付日期，截止日后现金流不计入结果；超出截止日的交易或需求拒绝计算。每笔 sales 给出 bond_id、face、trade_date、settlement_date、entitlement_cutoff、dirty_price_per_100、fee；requirements 每项 date 和 amount。数值可以是字符串或数字，日期为 YYYY-MM-DD。

已出售部分的权益归属：现金流日早于 entitlement_cutoff 的仍按原持仓归属；现金流日在该日期或之后时，扣除该次出售面值。该日期需由用户根据债券及交易条款提供；程序不会自动推定登记、除息、交易资格或节假日。为避免到期后的错误出售和到期日顺序歧义，本版要求出售交易日与结算日均严格早于到期本金支付日，收益权截止日不得晚于本金支付日；不满足时拒绝计算，并不表示其他交易安排在现实中必然不可行。不同批次出售累计面值不得超过起初持有面值。成交收益按全价×出售面值÷100减费用，现金在 settlement_date 入账，不另外重复加应计利息；净价不可直接填入。脚本未建模税务、保证金、卖空、借款、融资、交易失败或违约。

同日次序为已结算卖出、当日归属现金流、支出；这是情景假设，不保证真实结算和可用时间。若该日资金不足，程序显示未覆盖金额并消耗已有现金，后续收入不会倒填此前逾期支出；也不自动追加融资。数据必须按as_of确认，日期较早的现金流不重复计入。持仓面值、付款、报价和时间均由用户输入，脚本不联网核验真实性。

## 来源可靠性

材料分为合同条款、公开报告的陈述、使用者持仓/报价、情景假设四类。引用文件不自动证实其背后的现金支付；预测收益率和理论价格不自动代表可成交报价。区分现金足额、结算未确认、价格未知、输入不足等状态。
