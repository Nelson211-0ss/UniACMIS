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
  FingerprintIcon,
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
  /** Hidden from these roles even when `roles`/`permission` would allow it —
   * for a destination another entry already covers better for them. */
  hiddenFor?: string[];
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
    // Each of these has its own home — `/my` for a student, `/apply` for an
    // applicant, `/department` for a HoD — so listing the staff dashboard as
    // well would be one link too many pointing somewhere they cannot use.
    hiddenFor: ["student", "applicant", "hod"],
    section: "Overview",
  },

  // ----------------------------------------------------------- applicant
  {
    href: "/apply",
    label: "My Application",
    icon: FileTextIcon,
    permission: null,
    roles: ["applicant"],
    section: "Application",
    description: "Track and manage your admission application.",
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

  // ------------------------------------------------------------- department
  {
    href: "/department",
    label: "Department",
    icon: DashboardIcon,
    permission: null,
    roles: ["hod"],
    section: "Overview",
    description: "Your department at a glance.",
  },

  // ------------------------------------------------------ academic operations
  {
    href: "/examinations",
    label: "Examinations",
    icon: LayersIcon,
    permission: null,
    roles: ["lecturer", "hod", "examinations", "senate"],
    section: "Academic operations",
    description: "Mark entry, moderation, approvals and appeals.",
  },
  {
    href: "/attendance",
    label: "Attendance registers",
    icon: ClockIcon,
    permission: null,
    roles: ["lecturer", "hod", "examinations"],
    section: "Academic operations",
    description: "Mark a class session and manage eligibility waivers.",
  },
  {
    href: "/timetabling",
    label: "Timetable & rooms",
    icon: CalendarIcon,
    permission: null,
    roles: ["registrar", "examinations"],
    section: "Academic operations",
    description: "Rooms, the class timetable and the exam timetable.",
  },

  // -------------------------------------------------------------- registry
  {
    href: "/admissions",
    label: "Admissions",
    icon: UserPlusIcon,
    permission: "admissions.view_application",
    hiddenFor: ["applicant"],
    section: "Registry",
    description: "Applications, review, merit lists and offers.",
  },
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
    hiddenFor: ["applicant"],
    section: "Campus",
    description: "Browse the catalogue and your loans.",
  },
  {
    href: "/hostel",
    label: "Hostel",
    icon: BedIcon,
    permission: null,
    hiddenFor: ["applicant"],
    section: "Campus",
    description: "Room allocation and occupancy.",
  },
  {
    href: "/documents",
    label: "Documents",
    icon: FileTextIcon,
    permission: null,
    hiddenFor: ["applicant"],
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

  // ------------------------------------------------------------ configuration
  {
    href: "/curriculum",
    label: "Curriculum",
    icon: LayersIcon,
    permission: "curriculum.add_programme",
    section: "Configuration",
    description: "Faculties, departments, programmes, courses and versions.",
  },
  {
    href: "/academics",
    label: "Calendar & grading",
    icon: CalendarIcon,
    permission: "academics.change_semester",
    section: "Configuration",
    description: "Institution details, the academic calendar and grading scales.",
  },
  {
    href: "/users",
    label: "Users & roles",
    icon: UsersIcon,
    permission: "accounts.view_user",
    section: "Configuration",
    description: "Staff accounts and role assignment.",
  },
  {
    href: "/audit",
    label: "Audit trail",
    icon: FingerprintIcon,
    permission: "audit.view_auditlog",
    section: "Configuration",
    description: "The tamper-evident record of every change.",
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
    (item) =>
      (!item.permission || can(item.permission)) &&
      (!item.roles || hasRole(...item.roles)) &&
      !(item.hiddenFor && hasRole(...item.hiddenFor)),
  );
}
