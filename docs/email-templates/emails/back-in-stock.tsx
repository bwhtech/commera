import { Hr, Img, Section, Text } from '@react-email/components';
import {
	Button,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	PlaceholderTile,
	WasPrice,
	onSale,
	s,
} from '../kit/components';
import { type Sample, fill, imageUrl, money, t } from '../kit/data';

export default function BackInStock({
	brand,
	order,
	back_in_stock,
	copy,
	imageBase,
}: Sample) {
	const text = copy.back_in_stock;
	const item =
		order.items.find((row) => row.item_code === back_in_stock.item_code) ??
		order.items[0];
	const photo = imageUrl(imageBase, item.image, 'square');
	const values = {
		first_name: order.customer_first_name,
		item_name: item.item_name,
	};

	return (
		<EmailLayout
			layout="lookbook"
			preview={`${item.item_name} in ${item.variant} is back. ${money(
				item.rate,
			)}.`}
		>
			<Header brand={brand} />

			<Text style={s.caption}>Back in stock</Text>
			<Heading>{fill(text.heading, values)}</Heading>
			<Intro>{fill(text.intro, values)}</Intro>

			<Section style={{ marginTop: 28 }}>
				{photo ? (
					<Img
						src={photo}
						alt={item.item_name}
						width="560"
						height="560"
						style={{
							display: 'block',
							width: '100%',
							height: 'auto',
							borderRadius: t.radiusCard,
							backgroundColor: t.surfaceGray2,
						}}
					/>
				) : (
					<PlaceholderTile
						name={item.item_name}
						width="100%"
						height={360}
						fontSize={32}
					/>
				)}
				<Text style={{ ...s.title, fontSize: 17, marginTop: 16 }}>
					{item.item_name}
				</Text>
				<Text style={{ ...s.caption, fontSize: 14, marginTop: 4 }}>
					{item.variant}
				</Text>
				<Text
					style={{
						...s.num,
						margin: 0,
						marginTop: 8,
						fontFamily: t.font,
						fontSize: 17,
						fontWeight: t.medium,
						color: t.inkGray9,
					}}
				>
					{money(item.rate)}
					{onSale(item) && (
						<WasPrice amount={item.price_list_rate} fontSize={14} />
					)}
				</Text>
				<Button href={back_in_stock.product_url} marginTop={20}>
					{text.button}
				</Button>
			</Section>

			<Hr style={{ ...s.hr, margin: '32px 0 20px' }} />

			<Footer
				brand={brand}
				closing={fill(text.closing, values)}
				links={[
					{
						label: 'Stop these alerts',
						url: `${brand.store_url}/account/alerts`,
					},
				]}
				reason={`You're receiving this because you asked us to email you when this item is back.`}
			/>
		</EmailLayout>
	);
}
