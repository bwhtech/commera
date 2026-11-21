import {
	AmountPanel,
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ItemList,
	Totals,
	s,
} from '../kit/components';
import {
	type Sample,
	fill,
	money,
	orderTotals,
	orderValues,
} from '../kit/data';

export default function OrderCancelledClassic({
	brand,
	order,
	cancellation,
	copy,
	imageBase,
}: Sample) {
	const text = copy.order_cancelled;
	const { grand } = orderTotals(order);
	const values = { ...orderValues(order), reason: cancellation.reason };

	return (
		<EmailLayout
			preview={`Order ${order.name} is cancelled. ${money(
				grand,
			)} goes back to ${order.payment_method} in ${cancellation.refund_days}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<AmountPanel label="Your refund" amount={money(grand)}>
					Back to <b style={s.strong}>{order.payment_method}</b> within{' '}
					{cancellation.refund_days}.
				</AmountPanel>
				<Button href={order.order_url}>{text.button}</Button>
			</Card>

			<Card>
				<ItemList
					heading="Cancelled items"
					items={order.items}
					imageBase={imageBase}
				/>
				<Totals order={order} />
			</Card>

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
