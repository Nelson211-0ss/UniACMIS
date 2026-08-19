import type { ReactNode } from "react";

import {
  BarChartIcon,
  BedIcon,
  BookOpenIcon,
  BriefcaseIcon,
  CalendarIcon,
  ClockIcon,
  CreditCardIcon,
  DashboardIcon,
  FileTextIcon,
  InboxIcon,
  LayersIcon,
  MegaphoneIcon,
  UserGraduateIcon,
  UserPlusIcon,
  UsersIcon,
} from "@/components/icons";

export interface NavItem {
  href: string;
  label: string;
  icon: (props: { size?: number }) => ReactNode;
  /** Permission the API requires for the destination, or null for everyone. */
  permission: string | null;
  /** Shown only to one of these roles, or everyone if omitted. */
  roles?: string[];
  section: string;
  /** One line shown on the dashboard's quick-links card, not in the sidebar. */
  description?: string;
}

/** Any role that comes with a `staff_profile` — i.e. everyone except an
 * applicant or a student. Leave requests, appraisals and the rest of the
 * self-service HR surface are open to all of them, not just the `hr` role. */
export const STAFF_ROLES = [
  "lecturer",
  "hod",
  "registrar",
  "finance",
  "examinations",
  "senate",
  "hr",
  "library",
  "hostel",
  "ict_admin",
  "management",
];

export const NAV: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: DashboardIcon,
    permission: null,
    section: "Overview",
  },

  // ------------------------------------------------------------- student
  {
    href: "/my",
    label: "My portal",
    icon: LayersIcon,
    permission: null,
    roles: ["student"],
    section: "Student",
    description: "Your standing at a glance.",
  },
  {
    href: "/my/courses",
    label: "Course registration",
    icon: UserPlusIcon,
    permission: "enrollment.view_courseregistration",
    roles: ["student"],
    section: "Student",
    description: "Register or drop courses for the open semester.",
  },
  {
    href: "/my/timetable",
    label: "Timetable",
    icon: CalendarIcon,
    permission: "timetabling.view_timetableentry",
    roles: ["student"],
    section: "Student",
    description: "Weekly classes and the exam schedule.",
  },
  {
    href: "/my/results",
    label: "Results & appeals",
    icon: LayersIcon,
    permission: "examinations.view_mark",
    roles: ["student"],
    section: "Student",
    description: "Published grades, GPA and grade appeals.",
  },
  {
    href: "/my/attendance",
    label: "Attendance",
    icon: ClockIcon,
    permission: "attendance.view_sessionrecord",
    roles: ["student"],
    section: "Student",
    description: "Session attendance and exam eligibility.",
  },
  {
    href: "/my/finance",
    label: "Fees & payments",
    icon: CreditCardIcon,
    permission: "finance.view_invoice",
    roles: ["student"],
    section: "Student",
    description: "Invoices, receipts and your fee balance.",
  },

  // -------------------------------------------------------------- registry
  {
    href: "/students",
    label: "Students",
    icon: UsersIcon,
    permission: "registry.view_student",
    section: "Registry",
    description: "The student register.",
  },
  {
    href: "/students/new",
    label: "Admit a student",
    icon: UserPlusIcon,
    permission: "registry.add_student",
    section: "Registry",
    description: "Add a new student record.",
  },

  // ---------------------------------------------------------------- campus
  {
    href: "/library",
    label: "Library",
    icon: BookOpenIcon,
    permission: null,
    section: "Campus",
    description: "Browse the catalogue and your loans.",
  },
  {
    href: "/hostel",
    label: "Hostel",
    icon: BedIcon,
    permission: null,
    section: "Campus",
    description: "Room allocation and occupancy.",
  },
  {
    href: "/documents",
    label: "Documents",
    icon: FileTextIcon,
    permission: null,
    section: "Campus",
    description: "Transcript requests and issued certificates.",
  },
  {
    href: "/communications",
    label: "Announcements",
    icon: MegaphoneIcon,
    permission: null,
    section: "Campus",
    description: "Notices for your programme and the institution.",
  },

  // -------------------------------------------------------------- back office
  {
    href: "/finance",
    label: "Finance",
    icon: CreditCardIcon,
    permission: "finance.view_invoice",
    roles: ["finance", "management"],
    section: "Back office",
    description: "Fee structures, invoices, payments and refunds.",
  },
  {
    href: "/hr",
    label: "HR & leave",
    icon: BriefcaseIcon,
    permission: null,
    roles: STAFF_ROLES,
    section: "Back office",
    description: "Contracts, leave requests and appraisals.",
  },
  {
    href: "/alumni",
    label: "Alumni",
    icon: UserGraduateIcon,
    permission: "alumni.view_alumniprofile",
    section: "Back office",
    description: "Tracer profiles and alumni events.",
  },
  {
    href: "/reporting",
    label: "Reports & analytics",
    icon: BarChartIcon,
    permission: "reporting.view_dashboard",
    section: "Back office",
    description: "KPIs, statutory exports and custom reports.",
  },

  // ---------------------------------------------------------------- device
  {
    href: "/outbox",
    label: "Offline queue",
    icon: InboxIcon,
    permission: null,
    section: "Device",
    description: "Writes captured on this device, waiting to sync.",
  },
];

export function visibleNav(
  can: (permission: string) => boolean,
  hasRole: (...roles: string[]) => boolean,
): NavItem[] {
  return NAV.filter(
    (item) => (!item.permission || can(item.permission)) && (!item.roles || hasRole(...item.roles)),
  );
}
