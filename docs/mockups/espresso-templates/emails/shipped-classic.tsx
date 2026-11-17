import { Text } from '@react-email/components';
import {
	AddressBlock,
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ItemRow,
	ProgressSteps,
	ShipmentPanel,
	s,
} from '../kit/components';
import { type Sample, fill } from '../kit/data';

export default function ShippedClassic({
	brand,
	order,
	steps,
	shipment,
	copy,
	imageBase,
}: Sample) {
	const text = copy.shipped;
	const values = {
		first_name: order.customer_first_name,
		order_number: order.name,
	};
	const arrival = steps.at(-1);

	return (
		<EmailLayout
			layout="classic"
			preview={`Order ${order.name} shipped with ${shipment.carrier}. ${
				arrival?.pending_title ?? 'Arriving'
			} ${arrival?.date}.`}
		>
			<Header brand={brand} layout="classic" meta={`Order ${order.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<ProgressSteps steps={steps} detail={shipment.delay_note} />
				<ShipmentPanel shipment={shipment} />
				<Button href={shipment.tracking_url}>{text.button}</Button>
			</Card>

			<Card>
				<Text style={s.sectionTitle}>In this parcel</Text>
				{order.items.map((row) => (
					<ItemRow key={row.item_code} row={row} imageBase={imageBase} />
				))}
			</Card>

			<Card>
				<AddressBlock
					label="Shipping to"
					address={order.shipping}
					extraLines={[order.contact_mobile]}
				/>
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				reason={`You're receiving this because you placed an order at ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
