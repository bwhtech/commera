import { Hr, Section, Text } from '@react-email/components';
import {
	AddressBlock,
	Button,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ItemGrid,
	ProgressSteps,
	ShipmentPanel,
	s,
} from '../kit/components';
import { type Sample, fill, orderValues } from '../kit/data';

export default function ShippedLookbook({
	brand,
	order,
	steps,
	shipment,
	copy,
	imageBase,
}: Sample) {
	const text = copy.shipped;
	const values = orderValues(order);
	const arrival = steps.at(-1);

	return (
		<EmailLayout
			layout="lookbook"
			preview={`Order ${order.name} shipped with ${shipment.carrier}. ${
				arrival?.pending_title ?? 'Arriving'
			} ${arrival?.date}.`}
		>
			<Header brand={brand} />

			<Text style={s.caption}>
				Order {order.name}, shipped {shipment.shipped_on}
			</Text>
			<Heading>{fill(text.heading, values)}</Heading>
			<Intro>{fill(text.intro, values)}</Intro>

			<Section style={{ marginTop: 32 }}>
				<ProgressSteps
					steps={steps}
					marginTop={0}
					detail={shipment.delay_note}
				/>
				<ShipmentPanel shipment={shipment} marginTop={24} />
				<Button href={shipment.tracking_url}>{text.button}</Button>
			</Section>

			<ItemGrid items={order.items} imageBase={imageBase} />

			<Hr style={{ ...s.hr, margin: '8px 0 20px' }} />

			<AddressBlock label="Shipping to" address={order.shipping} bold={false} />

			<Hr style={{ ...s.hr, margin: '20px 0' }} />

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
