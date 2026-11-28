import {
	AddressBlock,
	BillingAddress,
	Button,
	Card,
	EmailLayout,
	FactBlock,
	Footer,
	Header,
	Heading,
	Intro,
	ItemList,
	NoteBlock,
	ProgressSteps,
	Totals,
	TwoColumns,
} from '../kit/components';
import {
	type Sample,
	fill,
	money,
	orderTotals,
	orderValues,
} from '../kit/data';

export default function OrderConfirmationClassic({
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
			preview={`Order ${order.name} confirmed. ${money(grand)}, arriving ${
				order.delivery_window
			}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<ProgressSteps steps={steps} />
				<Button href={order.order_url}>{text.button}</Button>
			</Card>

			<Card>
				<ItemList
					heading="Order summary"
					items={order.items}
					imageBase={imageBase}
				/>
				<Totals order={order} />
			</Card>

			{(order.customer_note || order.gift_message) && (
				<Card>
					<NoteBlock label="Your delivery note" body={order.customer_note} />
					<NoteBlock
						label="Gift message, printed on the card"
						body={order.gift_message}
						first={!order.customer_note}
					/>
				</Card>
			)}

			<Card>
				<AddressBlock
					label="Shipping to"
					address={order.shipping}
					extraLines={[order.contact_mobile]}
				/>
				<BillingAddress order={order} />
				<TwoColumns marginTop={16}>
					<FactBlock
						label="Payment"
						title={order.payment_method}
						detail={order.payment_status}
					/>
					<FactBlock
						label="Delivery"
						title={order.delivery_method}
						detail={`Arrives ${order.delivery_window}`}
					/>
				</TwoColumns>
			</Card>

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
