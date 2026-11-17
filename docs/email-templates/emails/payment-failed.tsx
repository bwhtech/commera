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

export default function PaymentFailed({
	brand,
	order,
	payment_failure,
	copy,
	imageBase,
}: Sample) {
	const text = copy.payment_failed;
	const { grand } = orderTotals(order);
	const values = {
		...orderValues(order),
		hold_hours: String(payment_failure.hold_hours),
	};

	return (
		<EmailLayout
			preview={`Payment for order ${order.name} didn't go through. We're holding it until ${payment_failure.held_until}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<AmountPanel label="To pay" amount={money(grand)}>
					Held until <b style={s.strong}>{payment_failure.held_until}</b>. Last
					tried with {payment_failure.attempted_method}.
				</AmountPanel>
				<Button href={payment_failure.payment_url}>{text.button}</Button>
			</Card>

			<Card>
				<ItemList
					heading="Order summary"
					items={order.items}
					imageBase={imageBase}
				/>
				<Totals order={order} totalLabel="To pay" />
			</Card>

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
