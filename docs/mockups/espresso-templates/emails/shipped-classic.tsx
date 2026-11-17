import {
	AddressBlock,
	Button,
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	ItemList,
	ProgressSteps,
	ShipmentPanel,
} from '../kit/components';
import { type Sample, fill, orderValues } from '../kit/data';

export default function ShippedClassic({
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
			preview={`Order ${order.name} shipped with ${shipment.carrier}. ${
				arrival?.pending_title ?? 'Arriving'
			} ${arrival?.date}.`}
		>
			<Header brand={brand} meta={`Order ${order.name}`} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<ProgressSteps steps={steps} detail={shipment.delay_note} />
				<ShipmentPanel shipment={shipment} />
				<Button href={shipment.tracking_url}>{text.button}</Button>
			</Card>

			<Card>
				<ItemList
					heading="In this parcel"
					items={order.items}
					imageBase={imageBase}
				/>
			</Card>

			<Card>
				<AddressBlock
					label="Shipping to"
					address={order.shipping}
					extraLines={[order.contact_mobile]}
				/>
			</Card>

			<Footer brand={brand} closing={fill(text.closing, values)} />
		</EmailLayout>
	);
}
