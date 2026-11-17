import { Hr, Section, Text } from '@react-email/components';
import {
	AddressBlock,
	BillingAddress,
	Button,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ItemGrid,
	ProgressSteps,
	Totals,
	s,
} from '../kit/components';
import {
	type Sample,
	fill,
	money,
	orderTotals,
	orderValues,
	t,
} from '../kit/data';

export default function OrderConfirmationLookbook({
	brand,
	order,
	steps,
	copy,
	imageBase,
}: Sample) {
	const text = copy.order_confirmation;
	const { grand } = orderTotals(order);
	const values = orderValues(order);

	return (
		<EmailLayout
			layout="lookbook"
			preview={`Order ${order.name} confirmed. ${money(grand)}, arriving ${
				order.delivery_window
			}.`}
		>
			<Header brand={brand} />

			<Text style={s.caption}>
				Order {order.name}, {order.transaction_date}, {order.transaction_time}
			</Text>
			<Heading>{fill(text.heading, values)}</Heading>
			<Intro>{fill(text.intro, values)}</Intro>

			<ItemGrid items={order.items} imageBase={imageBase} />
			<Totals order={order} />

			<Section style={{ marginTop: 32 }}>
				<ProgressSteps steps={steps} marginTop={0} />
				<Button href={order.order_url}>{text.button}</Button>
			</Section>

			{(order.customer_note || order.gift_message) && (
				<Section style={{ marginTop: 32 }}>
					{order.gift_message && (
						<>
							<Text
								style={{
									...s.para,
									fontSize: 20,
									lineHeight: '1.4',
									fontWeight: t.medium,
									letterSpacing: '-0.01em',
									color: t.inkGray9,
								}}
							>
								“{order.gift_message}”
							</Text>
							<Text style={{ ...s.muted, marginTop: 8 }}>
								Printed on the gift card
							</Text>
						</>
					)}
					{order.customer_note && (
						<Text style={{ ...s.para, marginTop: order.gift_message ? 20 : 0 }}>
							<span style={s.strong}>Delivery note: </span>
							{order.customer_note}
						</Text>
					)}
				</Section>
			)}

			<Hr style={{ ...s.hr, margin: '32px 0 20px' }} />

			<AddressBlock label="Shipping to" address={order.shipping} bold={false} />
			<BillingAddress order={order} bold={false} />

			<Hr style={{ ...s.hr, margin: '20px 0' }} />

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
