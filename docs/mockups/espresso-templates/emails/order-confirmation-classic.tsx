import { Column, Row, Section, Text } from "@react-email/components";
import {
	AddressBlock, Button, Card, EmailLayout, FactBlock, Footer, Header, Heading, Intro, ItemRow, NoteBlock, ProgressSteps, Totals, s,
} from "../kit/components";
import { type Sample, fill, money, orderTotals } from "../kit/data";

export default function OrderConfirmationClassic({ brand, order, steps, copy, imageBase }: Sample) {
	const text = copy.order_confirmation;
	const { grand } = orderTotals(order);
	const values = { first_name: order.customer_first_name, order_number: order.name };

	return (
		<EmailLayout layout="classic" preview={`Order ${order.name} confirmed. ${money(grand)}, arriving ${order.delivery_window}.`}>
			<Header brand={brand} layout="classic" meta={`Order ${order.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<ProgressSteps steps={steps} />
				<Button href={order.order_url}>{text.button}</Button>
			</Card>

			<Card>
				<Text style={s.sectionTitle}>Order summary</Text>
				{order.items.map((row) => (
					<ItemRow key={row.item_code} row={row} imageBase={imageBase} />
				))}
				<Totals order={order} layout="classic" />
			</Card>

			{(order.customer_note || order.gift_message) && (
				<Card>
					<NoteBlock label="Your delivery note" body={order.customer_note} />
					<NoteBlock label="Gift message, printed on the card" body={order.gift_message} first={!order.customer_note} />
				</Card>
			)}

			<Card>
				<AddressBlock label="Shipping to" address={order.shipping} extraLines={[order.contact_mobile]} />
				<Section style={{ marginTop: 16 }}>
					<AddressBlock
						label="Billing to"
						address={order.billing}
						emptyText="Same as shipping address"
						extraLines={[order.customer_tax_id && `GSTIN ${order.customer_tax_id}`]}
					/>
				</Section>
				<Row style={{ marginTop: 16 }}>
					<Column style={s.half}>
						<FactBlock label="Payment" title={order.payment_method} detail={order.payment_status} />
					</Column>
					<Column style={s.half}>
						<FactBlock label="Delivery" title={order.delivery_method} detail={`Arrives ${order.delivery_window}`} />
					</Column>
				</Row>
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				reason={`You're receiving this because you placed an order at ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
