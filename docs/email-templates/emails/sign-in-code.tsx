import { Text } from '@react-email/components';
import {
	Card,
	EmailLayout,
	Footer,
	Header,
	Heading,
	Intro,
	Panel,
	s,
} from '../kit/components';
import { type Sample, fill } from '../kit/data';

export default function SignInCode({ brand, sign_in, copy }: Sample) {
	const text = copy.sign_in_code;
	const values = { store_name: brand.name };

	return (
		<EmailLayout
			preview={`Your ${brand.name} sign-in code is ${sign_in.code}. It expires in ${sign_in.expires_in_minutes} minutes.`}
		>
			<Header brand={brand} />

			<Card first>
				<Heading>{fill(text.heading, values)}</Heading>
				<Intro>{fill(text.intro, values)}</Intro>
				<Panel padding="20px 16px">
					<Text
						style={{
							...s.title,
							...s.num,
							fontSize: 36,
							lineHeight: '1.1',
							letterSpacing: '0.16em',
							paddingLeft: '0.16em',
							textAlign: 'center',
						}}
					>
						{sign_in.code}
					</Text>
				</Panel>
				<Text style={{ ...s.para, marginTop: 16 }}>
					The code expires in {sign_in.expires_in_minutes} minutes.
				</Text>
				<Text style={{ ...s.para, marginTop: 4 }}>
					{fill(text.closing, values)}
				</Text>
			</Card>

			<Footer
				brand={brand}
				links={[]}
				reason={`You're receiving this because someone asked to sign in to ${brand.name} with this email address.`}
			/>
		</EmailLayout>
	);
}
