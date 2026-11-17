import { Section, Text } from '@react-email/components';
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
	Panel,
	ProgressSteps,
	s,
} from '../kit/components';
import { type Sample, fill } from '../kit/data';

export default function ReadyForPickup({
	brand,
	order,
	steps,
	pickup,
	copy,
	imageBase,
}: Sample) {
	const text = copy.ready_for_pickup;
	const values = {
		first_name: order.customer_first_name,
		order_number: order.name,
	};

	return (
		<EmailLayout
			layout="classic"
			preview={`Order ${order.name} is ready at ${pickup.store_name}. Collect it by ${pickup.collect_by}.`}
		>
			<Header brand={brand} layout="classic" meta={`Order ${order.name}`} />

			<Card first>
				<Heading layout="classic">{fill(text.heading, values)}</Heading>
				<Intro layout="classic">{fill(text.intro, values)}</Intro>
				<ProgressSteps steps={steps} />
				<Panel>
					<Text style={s.label}>Collect by</Text>
					<Text style={s.amount}>{pickup.collect_by}</Text>
					<Text style={{ ...s.address, marginTop: 6 }}>
						Bring your order number <b style={s.strong}>{order.name}</b> and a
						photo ID.
					</Text>
				</Panel>
				<Button href={pickup.directions_url}>{text.button}</Button>
			</Card>

			<Card>
				<AddressBlock label="Pick up from" address={pickup.address} />
				{pickup.hours.length > 0 && (
					<Section style={{ marginTop: 16 }}>
						<Text style={s.label}>Opening hours</Text>
						<Text style={s.address}>
							{pickup.hours.map((line, index) => (
								<span key={line}>
									{index > 0 && <br />}
									{line}
								</span>
							))}
						</Text>
					</Section>
				)}
			</Card>

			<Card>
				<Text style={s.sectionTitle}>To collect</Text>
				{order.items.map((row) => (
					<ItemRow key={row.item_code} row={row} imageBase={imageBase} />
				))}
			</Card>

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				reason={`You're receiving this because you placed an order at ${brand.name}.`}
			/>
		</EmailLayout>
	);
}
