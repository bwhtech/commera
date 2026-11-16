import { Column, Row, Text } from "@react-email/components";
import type { CSSProperties, ReactNode } from "react";
import { t } from "./data";

export type StepperStep = { title: string; date?: string; done: boolean };

export type StepperStatus = { label: string; date: string; detail?: string };

export type StepperProps = { steps: StepperStep[]; status: StepperStatus; onGray?: boolean };

const text: CSSProperties = { margin: 0, fontFamily: t.font, letterSpacing: "0.005em" };
const num: CSSProperties = { fontVariantNumeric: "tabular-nums" };
const cell: CSSProperties = { padding: 0, verticalAlign: "top" };

function stepTitle(step: StepperStep): CSSProperties {
	return { ...text, fontSize: 13, fontWeight: t.medium, lineHeight: "1.3", color: step.done ? t.inkGray9 : t.inkGray5 };
}

function currentStep(steps: StepperStep[]) {
	return [...steps].reverse().find((step) => step.done) ?? steps[0];
}

function Table({ children, style }: { children: ReactNode; style?: CSSProperties }) {
	return (
		<table role="presentation" cellPadding={0} cellSpacing={0} border={0} width="100%" style={{ borderCollapse: "collapse", ...style }}>
			<tbody>{children}</tbody>
		</table>
	);
}

function StatusLine({ status, size = 17 }: { status: StepperStatus; size?: number }) {
	return (
		<>
			<Text style={{ ...text, ...num, fontSize: size, fontWeight: t.semibold, lineHeight: "1.3", color: t.inkGray9 }}>
				{status.label} {status.date}
			</Text>
			{status.detail && <Text style={{ ...text, fontSize: 13, lineHeight: "1.4", color: t.inkGray5, marginTop: 2 }}>{status.detail}</Text>}
		</>
	);
}

function Bar({ steps, height, gap }: { steps: StepperStep[]; height: number; gap: number }) {
	return (
		<Table>
			<tr>
				{steps.map((step, index) => (
					<td key={step.title} width={`${100 / steps.length}%`} style={{ ...cell, paddingRight: index < steps.length - 1 ? gap : 0 }}>
						<div
							style={{
								height, lineHeight: `${height}px`, fontSize: 1, borderRadius: gap ? height : 0,
								backgroundColor: step.done ? t.inkGreen6 : t.outlineGray2,
								...(gap ? {} : roundEnds(index, steps.length, height)),
							}}
						>
							&nbsp;
						</div>
					</td>
				))}
			</tr>
		</Table>
	);
}

function roundEnds(index: number, count: number, height: number): CSSProperties {
	if (index === 0) return { borderTopLeftRadius: height, borderBottomLeftRadius: height };
	if (index === count - 1) return { borderTopRightRadius: height, borderBottomRightRadius: height };
	return {};
}

function Labels({ steps, marginTop }: { steps: StepperStep[]; marginTop: number }) {
	return (
		<Table style={{ marginTop }}>
			<tr>
				{steps.map((step, index) => (
					<td key={step.title} width={`${100 / steps.length}%`} style={{ ...cell, paddingRight: index < steps.length - 1 ? 4 : 0 }}>
						<Text style={{ ...stepTitle(step), fontSize: 12 }}>{step.title}</Text>
					</td>
				))}
			</tr>
		</Table>
	);
}

export function AmazonStepper({ steps, status }: StepperProps) {
	return (
		<div style={{ marginTop: 24 }}>
			<StatusLine status={status} />
			<div style={{ marginTop: 14 }}>
				<Bar steps={steps} height={6} gap={0} />
			</div>
			<Labels steps={steps} marginTop={8} />
		</div>
	);
}

export function AppleStepper({ steps, status }: StepperProps) {
	const current = currentStep(steps);
	return (
		<div style={{ marginTop: 24 }}>
			<Row>
				<Column style={{ verticalAlign: "bottom" }}>
					<Text style={{ ...text, fontSize: 15, fontWeight: t.semibold, lineHeight: "1.3", color: t.inkGray9 }}>{current.title}</Text>
				</Column>
				<Column align="right" style={{ verticalAlign: "bottom" }}>
					<Text style={{ ...text, ...num, fontSize: 13, lineHeight: "1.3", color: t.inkGray5 }}>
						{status.label === current.title ? status.date : `${status.label} ${status.date}`}
					</Text>
				</Column>
			</Row>
			<div style={{ marginTop: 10 }}>
				<Bar steps={steps} height={4} gap={4} />
			</div>
			{status.detail && <Text style={{ ...text, fontSize: 13, lineHeight: "1.4", color: t.inkGray5, marginTop: 8 }}>{status.detail}</Text>}
		</div>
	);
}

const markerSize = 16;

function Marker({ step }: { step: StepperStep }) {
	return (
		<div
			style={{
				width: step.done ? markerSize : markerSize - 4, height: step.done ? markerSize : markerSize - 4, borderRadius: "50%",
				border: step.done ? "none" : `2px solid ${t.inkGray3}`, backgroundColor: step.done ? t.inkGreen6 : t.surfaceBase,
				color: t.inkWhite, fontSize: 10, fontWeight: 700, lineHeight: `${markerSize}px`, textAlign: "center", fontFamily: t.font,
			}}
		>
			{step.done ? "✓" : ""}
		</div>
	);
}

function Connector({ done }: { done: boolean }) {
	return <div style={{ height: 2, lineHeight: "2px", fontSize: 1, backgroundColor: done ? t.inkGreen6 : t.outlineGray2, marginTop: 7 }}>&nbsp;</div>;
}

export function ShopifyStepper({ steps }: StepperProps) {
	return (
		<Table style={{ marginTop: 24 }}>
			<tr>
				{steps.map((step, index) => (
					<td key={step.title} width={`${100 / steps.length}%`} style={cell}>
						<Table>
							<tr>
								<td width={markerSize} style={cell}>
									<Marker step={step} />
								</td>
								<td style={{ ...cell, paddingLeft: 4, paddingRight: 4 }}>
									{index < steps.length - 1 && <Connector done={steps[index + 1].done} />}
								</td>
							</tr>
						</Table>
						<Text style={{ ...stepTitle(step), fontSize: 12, marginTop: 8 }}>{step.title}</Text>
						<Text style={{ ...text, ...num, fontSize: 12, lineHeight: "1.4", color: t.inkGray5, marginTop: 1 }}>{step.date ?? " "}</Text>
					</td>
				))}
			</tr>
		</Table>
	);
}

export function FlipkartStepper({ steps, status }: StepperProps) {
	return (
		<div style={{ marginTop: 24 }}>
			<Table>
				{steps.map((step, index) => {
					const last = index === steps.length - 1;
					return (
						<tr key={step.title}>
							<td width={24} style={cell}>
								<Marker step={step} />
								{!last && (
									<div
										style={{
											width: 2, height: 18, fontSize: 1, lineHeight: "18px", margin: "3px 0 3px 7px",
											backgroundColor: steps[index + 1].done ? t.inkGreen6 : t.outlineGray2,
										}}
									>
										&nbsp;
									</div>
								)}
							</td>
							<td style={{ ...cell, paddingLeft: 10 }}>
								<Text style={{ ...stepTitle(step), fontSize: 14, lineHeight: `${markerSize}px` }}>{step.title}</Text>
							</td>
							<td align="right" style={cell}>
								<Text style={{ ...text, ...num, fontSize: 13, lineHeight: `${markerSize}px`, color: t.inkGray5, textAlign: "right" }}>
									{step.date && !step.done ? `Expected ${step.date}` : (step.date ?? "")}
								</Text>
							</td>
						</tr>
					);
				})}
			</Table>
			{status.detail && <Text style={{ ...text, fontSize: 13, lineHeight: "1.4", color: t.inkGray5, marginTop: 10 }}>{status.detail}</Text>}
		</div>
	);
}

export function HimsStepper({ steps, status }: StepperProps) {
	return (
		<div style={{ marginTop: 22 }}>
			<StatusLine status={status} size={14} />
			<div style={{ marginTop: 12 }}>
				<Bar steps={steps} height={3} gap={8} />
			</div>
			<Labels steps={steps} marginTop={8} />
		</div>
	);
}

export function NikeStepper({ steps, status, onGray }: StepperProps) {
	const current = currentStep(steps);
	return (
		<div style={{ marginTop: 22, backgroundColor: onGray ? t.surfaceBase : t.surfaceGray2, borderRadius: t.radiusThumb, padding: "14px 16px" }}>
			{current.title !== status.label && (
				<Text style={{ ...text, fontSize: 12, color: t.inkGreen6, fontWeight: t.medium, marginBottom: 4 }}>{current.title}</Text>
			)}
			<StatusLine status={status} size={15} />
		</div>
	);
}
