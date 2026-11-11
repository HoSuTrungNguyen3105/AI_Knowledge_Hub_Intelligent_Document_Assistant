import { notFound } from "next/navigation";
import { PhasePlaceholder } from "../../../components/phase-placeholder";
import { sections } from "../../../utils/navigation";

export function generateStaticParams() { return Object.keys(sections).map((section) => ({ section })); }
export const dynamicParams = false;
export async function generateMetadata({ params }) {
  const { section } = await params;
  return { title: sections[section]?.title || "Không tìm thấy" };
}
export default async function SectionPage({ params }) {
  const { section } = await params;
  if (!Object.hasOwn(sections, section)) notFound();
  return <PhasePlaceholder section={sections[section]} />;
}
